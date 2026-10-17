"""
living.py — a realistic talking presenter from ONE portrait, on CPU, at no cost.

How it works (all our own code; MediaPipe Face Mesh is Apache-2.0, OpenCV is Apache-2.0):

  1. MediaPipe maps 478 points on the face once (lips, jaw, eyelids, irises).
  2. Rhubarb Lip Sync (MIT) turns the voice into timed mouth shapes; each shape becomes a target
     (jaw opening, mouth width). Targets are eased frame to frame like real muscles, never snapped.
  3. Each frame, a smooth warp field moves the jaw, chin and lips (and the eyelids for blinks); the opened mouth
     is filled with a shaded mouth interior, upper teeth and tongue, feathered into the lips.
  4. The whole head drifts, tilts and nods very slightly, with breathing, so he is never frozen.

    portrait (jpg/png, face looking at camera) + voice.wav ──► talking.mp4 / frames

Quality depends on the portrait: front-facing, mouth closed and relaxed, even light, face at least ~300 px wide.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

FPS = 30

# MediaPipe Face Mesh indices
LIPS_OUT_UP = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291]
LIPS_OUT_LO = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291]
LIPS_IN_UP = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]
LIPS_IN_LO = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]
JAW = [58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288]
CHIN = [152, 148, 377, 175, 199, 200, 18]
ANCHORS = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 21, 54, 103, 67, 109, 127, 162, 234, 93, 132,
           1, 4, 5, 195, 197, 6, 168, 2, 98, 327, 129, 358, 33, 133, 263, 362, 70, 300, 105, 334, 116, 345, 123, 352]
EYE_L_UP, EYE_L_LO = [246, 161, 160, 159, 158, 157, 173], [7, 163, 144, 145, 153, 154, 155]
EYE_R_UP, EYE_R_LO = [466, 388, 387, 386, 385, 384, 398], [249, 390, 373, 374, 380, 381, 382]

# Rhubarb shape -> (jaw opening 0..1, mouth width factor, teeth visible 0..1)
SHAPES = {
    "X": (0.00, 1.00, 0.0),   # rest
    "A": (0.00, 0.98, 0.0),   # M B P: lips pressed
    "B": (0.16, 1.03, 0.9),   # most consonants: teeth slightly apart
    "C": (0.45, 1.04, 0.8),   # EH, AE
    "D": (0.85, 1.06, 0.6),   # AA: wide open
    "E": (0.42, 0.86, 0.3),   # AO, ER: rounded
    "F": (0.20, 0.74, 0.0),   # UW, OW, W: puckered
    "G": (0.10, 1.00, 1.0),   # F V: teeth on lower lip
    "H": (0.42, 1.02, 0.7),   # L: tongue up
}


@dataclass
class Face:
    img: np.ndarray                      # BGR portrait
    lm: np.ndarray                       # 478 x 2 landmarks (pixels)
    mouth_w: float = 0.0
    centre: tuple = (0.0, 0.0)
    extra: dict = field(default_factory=dict)


def detect(img: np.ndarray) -> Face:
    import mediapipe as mp
    h, w = img.shape[:2]
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=True, max_num_faces=1) as fm:
        res = fm.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        raise ValueError("no face found in the portrait")
    lm = np.array([[p.x * w, p.y * h] for p in res.multi_face_landmarks[0].landmark], dtype=np.float32)
    mw = float(np.linalg.norm(lm[291] - lm[61]))
    return Face(img=img, lm=lm, mouth_w=mw, centre=tuple(lm[1]))


def _field(shape: tuple[int, int], src: np.ndarray, disp: np.ndarray, sigma: float, step: int = 4) -> np.ndarray:
    """Smooth displacement field from control points (Gaussian-weighted, normalised), computed on a coarse grid
    and upsampled. Anchors (disp 0) keep the warp local to the jaw and mouth."""
    h, w = shape
    gy, gx = np.mgrid[0:h:step, 0:w:step].astype(np.float32)
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    d2 = ((pts[:, None, :] - src[None, :, :]) ** 2).sum(-1)
    wgt = np.exp(-d2 / (2 * sigma * sigma))
    num = wgt @ disp
    den = wgt.sum(1, keepdims=True) + 1e-3
    out = (num / den) * np.clip(den, 0, 1)          # far from every control point: no movement
    out = out.reshape(gy.shape[0], gy.shape[1], 2)
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)


def profile(x: float, cx: float, mw: float) -> float:
    """How much of the opening a lip point gets: all of it at the centre, little at the corners (an oval mouth)."""
    u = min(1.0, abs(x - cx) / (0.5 * mw))
    return 0.12 + 0.88 * math.cos(u * math.pi / 2) ** 1.4


def _controls(face: Face, jaw: float, width: float, blink: float):
    lm, mw = face.lm, face.mouth_w
    drop = jaw * 0.42 * mw                            # how far the lower lip and chin travel at full opening
    pts, dsp = [], []

    def add(idx, dx, dy):
        for i in idx:
            pts.append(lm[i]); dsp.append((dx, dy))

    cx = (lm[61][0] + lm[291][0]) / 2
    for i in LIPS_IN_LO + LIPS_OUT_LO[1:-1]:
        pts.append(lm[i]); dsp.append(((lm[i][0] - cx) * (width - 1), drop * profile(lm[i][0], cx, mw)))
    for i in LIPS_IN_UP[1:-1] + LIPS_OUT_UP[1:-1]:
        pts.append(lm[i]); dsp.append(((lm[i][0] - cx) * (width - 1), -0.10 * drop * profile(lm[i][0], cx, mw)))
    for i in (61, 78, 291, 308):                      # mouth corners: spread or round, drop a little
        pts.append(lm[i]); dsp.append(((lm[i][0] - cx) * (width - 1) * 1.1, 0.35 * drop))
    for i in CHIN:
        pts.append(lm[i]); dsp.append((0, 0.92 * drop))
    for i in JAW:                                     # the jaw line hinges: more at the chin, less at the ears
        k = 1 - min(1, abs(lm[i][0] - cx) / (1.6 * mw))
        pts.append(lm[i]); dsp.append((0, drop * (0.25 + 0.6 * k)))
    for i in ANCHORS:
        pts.append(lm[i]); dsp.append((0, 0))
    return np.array(pts, np.float32), np.array(dsp, np.float32), drop


def _eye_controls(face: Face, blink: float):
    """Upper lids come down onto the lower lids; brows and eye corners hold still."""
    lm = face.lm
    pts, dsp = [], []
    for up, lo in ((EYE_L_UP, EYE_L_LO), (EYE_R_UP, EYE_R_LO)):
        for a, b in zip(up, lo):
            gap = lm[b][1] - lm[a][1]
            pts.append(lm[a]); dsp.append((0, gap * blink * 1.05))   # the lid skin slides down over the eye
    for i in (33, 133, 263, 362, 70, 63, 105, 66, 107, 300, 293, 334, 296, 336, 6, 197):
        pts.append(lm[i]); dsp.append((0, 0))
    return np.array(pts, np.float32), np.array(dsp, np.float32)


def mouth_texture(open_photo: np.ndarray) -> dict:
    """The real inside of the presenter's mouth (teeth, tongue, shadow) from a photo of him saying 'ah':
    the area inside his lips, cut out once and reused for every opening."""
    f = detect(open_photo)
    poly = np.array([f.lm[i] for i in LIPS_IN_UP] + [f.lm[i] for i in LIPS_IN_LO[::-1]], np.float32)
    x, y, w, h = cv2.boundingRect(poly.astype(np.int32))
    tex = open_photo[y:y + h, x:x + w].copy()
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [(poly - [x, y]).astype(np.int32)], 255)
    return {"tex": tex, "mask": mask, "width": float(np.linalg.norm(f.lm[308] - f.lm[78]))}


def _real_interior(out: np.ndarray, up: np.ndarray, lo: np.ndarray, real: dict) -> bool:
    """Lays the real mouth interior into the opened lips: scaled to the opening's width, anchored at the upper
    teeth, cropped to the opening's height, feathered at the lips."""
    poly = np.concatenate([up, lo[::-1]]).astype(np.int32)
    x, y, bw, bh = cv2.boundingRect(poly)
    if bw < 6 or bh < 3:
        return False
    tex = real["tex"]
    k = bw / tex.shape[1]
    th = max(1, int(round(tex.shape[0] * k)))
    t = cv2.resize(tex, (bw, th), interpolation=cv2.INTER_CUBIC)
    if th < bh:   # a very wide opening: extend the bottom of the mouth (tongue, shadow) downwards
        t = cv2.copyMakeBorder(t, 0, bh - th, 0, 0, cv2.BORDER_REPLICATE)
    t = t[:bh]
    h, w = out.shape[:2]
    x1, y1 = min(w, x + bw), min(h, y + bh)
    if x1 <= x or y1 <= y or x < 0 or y < 0:
        return False
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [poly], 255)
    soft = (cv2.GaussianBlur(mask, (0, 0), 1.1) / 255.0)[y:y1, x:x1, None]
    region = out[y:y1, x:x1].astype(np.float32)
    out[y:y1, x:x1] = (region * (1 - soft) + t[: y1 - y, : x1 - x].astype(np.float32) * soft).astype(np.uint8)
    return True


def _mouth_interior(out: np.ndarray, up: np.ndarray, lo: np.ndarray, teeth: float, jaw: float, mw: float) -> None:
    """Fills the opened mouth: dark throat, upper teeth under the upper lip, tongue low, feathered edges."""
    poly = np.concatenate([up, lo[::-1]]).astype(np.int32)
    h, w = out.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [poly], 255)
    if mask.sum() < 255 * 6:
        return
    x, y, bw, bh = cv2.boundingRect(poly)
    layer = np.zeros_like(out)
    layer[:] = (16, 18, 42)                                           # deep mouth, warm (BGR)
    yy = np.arange(h)[:, None].repeat(w, 1)
    shade = np.clip((yy - y) / max(bh, 1), 0, 1)[..., None]
    layer = (layer * (0.7 + 0.5 * shade)).astype(np.uint8)
    if teeth > 0:
        th = max(2, int(min(bh * 0.36, 0.085 * mw) * (0.6 + 0.4 * teeth)))
        tmask = np.zeros((h, w), np.uint8)
        top = np.concatenate([up, up[::-1] + [0, th]]).astype(np.int32)
        cv2.fillPoly(tmask, [top], 255)
        xx = np.arange(w)[None, :].repeat(h, 0)
        side = np.clip(1 - np.abs(xx - (x + bw / 2)) / max(bw / 2, 1), 0, 1)[..., None]   # 1 centre, 0 corners
        tcol = np.full(out.shape, (150, 182, 222), np.float32) * (0.66 + 0.34 * side) * (0.9 + 0.1 * (1 - shade))   # warm ivory, darker at the corners
        tcol = tcol.astype(np.uint8)
        a = (cv2.GaussianBlur(tmask, (0, 0), 1.8) / 255.0 * teeth * 0.9)[..., None]
        layer = (layer * (1 - a) + tcol * a).astype(np.uint8)
    if jaw > 0.3:                                                     # tongue rests low in a wide mouth
        tm = np.zeros((h, w), np.uint8)
        cv2.ellipse(tm, (x + bw // 2, y + int(bh * 0.95)), (int(bw * 0.32), int(bh * 0.28)), 0, 180, 360, 255, -1)
        a = (cv2.GaussianBlur(tm, (0, 0), 2) / 255.0 * 0.85)[..., None]
        layer = (layer * (1 - a) + np.full_like(out, (70, 72, 150)) * a).astype(np.uint8)
    soft = (cv2.GaussianBlur(mask, (0, 0), 1.1) / 255.0)[..., None]
    out[:] = (out * (1 - soft) + layer * soft).astype(np.uint8)


def frame(face: Face, jaw: float, width: float, blink: float, head: tuple[float, float, float] = (0, 0, 0)) -> np.ndarray:
    """One frame of the portrait with the given jaw opening, mouth width, eyelid closure and head pose
    (dx px, dy px, degrees)."""
    img = face.img
    h, w = img.shape[:2]
    src, dsp, drop = _controls(face, jaw, width, blink)
    dst = src + dsp
    sigma = 0.30 * face.mouth_w
    fld = _field((h, w), dst, dsp, sigma)                      # backward map: sample where each pixel came from
    if blink > 0:
        esrc, edsp = _eye_controls(face, blink)
        fld = fld + _field((h, w), esrc + edsp, edsp, 0.07 * face.mouth_w, step=2)
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    out = cv2.remap(img, gx - fld[..., 0], gy - fld[..., 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    lm = face.lm
    cx = (lm[61][0] + lm[291][0]) / 2
    lo = np.array([lm[i] for i in LIPS_IN_LO], np.float32)
    lo[:, 1] += np.array([drop * profile(x, cx, face.mouth_w) for x in lo[:, 0]])
    up = np.array([lm[i] for i in LIPS_IN_UP], np.float32)
    up[:, 1] -= np.array([0.10 * drop * profile(x, cx, face.mouth_w) for x in up[:, 0]])
    up[:, 0] = cx + (up[:, 0] - cx) * width
    lo[:, 0] = cx + (lo[:, 0] - cx) * width
    if drop > 0.6:
        real = face.extra.get("mouth")
        if not (real and _real_interior(out, up, lo, real)):
            _mouth_interior(out, up, lo, SHAPES_TEETH.get("current", 0.7), jaw, face.mouth_w)
    dx, dy, deg = head
    if dx or dy or deg:
        m = cv2.getRotationMatrix2D(face.centre, deg, 1.0)
        m[:, 2] += (dx, dy)
        out = cv2.warpAffine(out, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    return out


SHAPES_TEETH: dict = {}


def performance(cues: list[dict], duration: float, seed: int = 0) -> list[tuple[float, float, float, float, tuple]]:
    """(jaw, width, teeth, blink, head) for every frame: shapes eased like muscles, natural blinks, a living head."""
    n = max(1, round(duration * FPS))
    target = [SHAPES["X"]] * n
    for c in cues:
        a, b = int(c["start"] * FPS), int(c["end"] * FPS)
        for i in range(max(0, a), min(n, max(b, a + 1))):
            target[i] = SHAPES.get(c["value"], SHAPES["X"])
    rng = random.Random(seed)
    blinks = set()
    t = rng.uniform(0.8, 1.8)
    while t * FPS < n - 5:
        i = int(t * FPS)
        for k, v in enumerate((0.45, 1.0, 1.0, 0.6, 0.2)):
            blinks.add((i + k, v))
        t += rng.uniform(2.6, 5.2)
    blink_at = dict(blinks)
    out, j, wd, te = [], 0.0, 1.0, 0.0
    speak = 0.0
    for i in range(n):
        tj, tw, tt = target[i]
        nxt = target[min(n - 1, i + 2)]                 # anticipate: muscles start moving before the sound
        tj = 0.65 * tj + 0.35 * nxt[0]
        j += (tj - j) * 0.55
        wd += (tw - wd) * 0.45
        te += (tt - te) * 0.5
        speak = 0.92 * speak + 0.08 * (1.0 if tj > 0.1 else 0.0)
        s = i / FPS
        head = (2.2 * math.sin(2 * math.pi * s / 5.3) + 1.2 * math.sin(2 * math.pi * s / 2.1),
                1.6 * math.sin(2 * math.pi * s / 3.7) + 3.0 * speak * math.sin(2 * math.pi * s / 0.9) * 0.4,
                0.9 * math.sin(2 * math.pi * s / 6.1) + 0.5 * speak * math.sin(2 * math.pi * s / 1.7))
        out.append((max(0.0, j), wd, te, blink_at.get(i, 0.0), head))
    return out


def render(face: Face, cues: list[dict], duration: float, out_dir: Path, seed: int = 0) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    perf = performance(cues, duration, seed)
    for i, (jaw, width, teeth, blink, head) in enumerate(perf):
        SHAPES_TEETH["current"] = teeth
        cv2.imwrite(str(out_dir / f"p{i:05d}.jpg"), frame(face, jaw, width, blink, head), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return len(perf)


# ---------------------------------------------------------------------------
# The talking clip and its place in the Reel
# ---------------------------------------------------------------------------
PIP_W, PIP_H = 460, 560          # the presenter's window on a 1080x1920 Reel
MARGIN = 1.12                    # rendered a little larger so head motion never shows an edge


def head_crop(img: np.ndarray, face: Face, size: tuple[int, int]) -> np.ndarray:
    """Head and shoulders, the face a little above centre, scaled to `size` (w, h)."""
    lm = face.lm
    top, chin = lm[10][1], lm[152][1]
    fh = chin - top
    w, h = size
    box_h = fh * 2.35
    box_w = box_h * w / h
    cx, cy = lm[1][0], top + fh * 0.62
    x0, y0 = int(round(cx - box_w / 2)), int(round(cy - box_h * 0.40))
    x1, y1 = int(round(x0 + box_w)), int(round(y0 + box_h))
    pad = max(0, -x0, -y0, x1 - img.shape[1], y1 - img.shape[0])
    if pad:
        img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        x0, y0, x1, y1 = x0 + pad, y0 + pad, x1 + pad, y1 + pad
    return cv2.resize(img[y0:y1, x0:x1], (w, h), interpolation=cv2.INTER_AREA)


def talk(portrait: Path, wav: Path, script: str, out: Path, ff: str, seed: int = 0) -> Path:
    """The talking presenter as an mp4 (PIP_W x PIP_H, no audio), exactly as long as the voice."""
    import subprocess
    import tempfile
    import presenter
    img = cv2.imread(str(portrait))
    if img is None:
        raise ValueError(f"cannot read portrait {portrait}")
    big = (int(PIP_W * MARGIN) // 2 * 2, int(PIP_H * MARGIN) // 2 * 2)
    crop = head_crop(img, detect(img), big)
    face = detect(crop)
    open_photo = portrait.with_name("mouth-open.jpg")       # optional: him saying "ah", for real teeth
    if open_photo.exists():
        try:
            face.extra["mouth"] = mouth_texture(cv2.imread(str(open_photo)))
        except Exception as e:
            print(f"  mouth photo not used: {e}")
    dur = presenter.seconds(wav)
    cues = presenter.cues(wav, script)
    with tempfile.TemporaryDirectory() as t:
        n = render(face, cues, dur, Path(t), seed)
        ox, oy = (big[0] - PIP_W) // 2, (big[1] - PIP_H) // 2
        subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(Path(t) / "p%05d.jpg"),
                        "-vf", f"crop={PIP_W}:{PIP_H}:{ox}:{oy},format=yuv420p", "-frames:v", str(n),
                        "-c:v", "libx264", "-preset", "medium", "-crf", "16", str(out)], check=True)
    return out


def overlay_graph(base_label: str, pip_label: str, out_label: str, right: int = 36, bottom: int = 150) -> str:
    """ffmpeg filter: the presenter's window bottom-right with rounded corners, a thin light edge and a shadow,
    like a live studio feed in the corner of the story."""
    r = 28
    return (f"[{pip_label}]format=yuva420p,geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':"
            f"a='if(gt(abs(W/2-X),W/2-{r})*gt(abs(H/2-Y),H/2-{r}),"
            f"if(lte(hypot({r}-(W/2-abs(W/2-X)),{r}-(H/2-abs(H/2-Y))),{r}),255,0),255)'[pr];"
            f"color=c=white@0.55:s={PIP_W + 6}x{PIP_H + 6},format=yuva420p,geq=lum='p(X,Y)':cb='p(X,Y)':cr='p(X,Y)':"
            f"a='if(gt(abs(W/2-X),W/2-{r + 3})*gt(abs(H/2-Y),H/2-{r + 3}),"
            f"if(lte(hypot({r + 3}-(W/2-abs(W/2-X)),{r + 3}-(H/2-abs(H/2-Y))),{r + 3}),140,0),140)'[edge];"
            f"[{base_label}][edge]overlay=x=W-w-{right - 3}:y=H-h-{bottom - 3}:shortest=0[b1];"
            f"[b1][pr]overlay=x=W-w-{right}:y=H-h-{bottom}:eof_action=repeat[{out_label}]")
