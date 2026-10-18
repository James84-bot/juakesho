"""
rig.py — the presenter rebuilt in code from one photo, in separate layers, so every part moves like a person.

    background   cut away and replaced by a studio backdrop drawn in code (depth-of-field lights)
    body         shoulders and chest: breathing, a slow settle; never turns with the head
    head         turns, nods and tilts in 3D (MediaPipe's face mesh gives every point a depth), so the nose
                 moves more than the ears; the neck bends smoothly between head and body
    face         eyelids that slide down to close (real blinks), eyes that look around, brows that lift on
                 stressed words, a mouth that follows the voice (with his real mouth photo), a small smile
    camera       slow push-in, drift, grain, vignette

The old presenter moved the whole picture (background included) and dragged the eye down to blink.

Runs in the face environment (MediaPipe), as living.py does:
    python rig.py talk <portrait> <voice.wav> <script.txt> <out.mp4> <ffmpeg> [seed]
"""
from __future__ import annotations

import math
import random
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

import living

FPS = 30
OUT_W, OUT_H = 1080, 960            # the presenter's half of the Reel (takes.TAKE_H)
WORK = 1.10                         # rendered a little larger: the camera moves inside it

# MediaPipe face mesh indices
L_UP = [33, 246, 161, 160, 159, 158, 157, 173, 133]      # his right eye (image left): upper lid, corner to corner
L_LO = [33, 7, 163, 144, 145, 153, 154, 155, 133]
R_UP = [362, 398, 384, 385, 386, 387, 388, 466, 263]
R_LO = [362, 382, 381, 380, 374, 373, 390, 249, 263]
L_IRIS, R_IRIS = [468, 469, 470, 471, 472], [473, 474, 475, 476, 477]
L_BROW = [70, 63, 105, 66, 107, 46, 53, 52, 65, 55]
R_BROW = [300, 293, 334, 296, 336, 276, 283, 282, 295, 285]
EYE_RING = L_UP + L_LO + R_UP + R_LO


@dataclass
class Rig:
    img: np.ndarray            # BGR, working size
    alpha: np.ndarray          # person matte 0..1
    lm: np.ndarray             # 478 x 2 (px)
    z: np.ndarray              # 478 depth (px, smaller = nearer the camera)
    depth: np.ndarray          # H x W depth for the head
    head_w: np.ndarray         # H x W: 1 = moves with the head, 0 = body / background
    breath_w: np.ndarray       # H x W: how much breathing lifts each pixel
    pivot: tuple               # (x, y, z) the head turns about (top of the neck)
    face: living.Face
    fw: float                  # face width px
    fh: float                  # face height px
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# building the rig from the photo
# ---------------------------------------------------------------------------
def _mesh(img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    import mediapipe as mp
    h, w = img.shape[:2]
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=True, max_num_faces=1) as fm:
        res = fm.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        raise ValueError("no face found in the portrait")
    pts = res.multi_face_landmarks[0].landmark
    return (np.array([[p.x * w, p.y * h] for p in pts], np.float32),
            np.array([p.z * w for p in pts], np.float32))


def _matte(img: np.ndarray) -> np.ndarray:
    """The person, cut from the background: MediaPipe selfie segmentation, edges refined on the photo."""
    import mediapipe as mp
    with mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0) as seg:
        m = seg.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).segmentation_mask.astype(np.float32)
    m = cv2.GaussianBlur(m, (0, 0), 1.2)
    m = np.clip((m - 0.25) / 0.5, 0, 1)             # a firmer edge than the raw probability
    try:   # follow the photo's real edges (hair) where the guided filter is available
        m = cv2.ximgproc.guidedFilter(img, m, 8, 1e-3)
    except Exception:
        pass
    m = cv2.erode(np.clip(m, 0, 1), np.ones((3, 3), np.uint8), iterations=1)   # no halo of the old background
    return np.clip(cv2.GaussianBlur(m, (0, 0), 0.8), 0, 1)


def _smooth_fill(shape, pts: np.ndarray, vals: np.ndarray, sigma: float, step: int = 8) -> np.ndarray:
    """A smooth field through scattered values (normalised Gaussian weights), on a coarse grid, upsampled."""
    h, w = shape
    gx, gy = np.meshgrid(np.arange(0, w, step, dtype=np.float32), np.arange(0, h, step, dtype=np.float32))
    num = np.zeros_like(gx)
    den = np.full_like(gx, 1e-6)
    for (x, y), v in zip(pts, vals):
        k = np.exp(-((gx - x) ** 2 + (gy - y) ** 2) / (2 * sigma ** 2))
        num += k * v
        den += k
    return cv2.resize(num / den, (w, h), interpolation=cv2.INTER_CUBIC)


def build(portrait: Path) -> Rig:
    src = cv2.imread(str(portrait))
    if src is None:
        raise ValueError(f"cannot read {portrait}")
    work = (int(OUT_W * WORK) // 2 * 2, int(OUT_H * WORK) // 2 * 2)
    face0 = living.detect(src)
    lm0 = face0.lm
    fh0 = lm0[152][1] - lm0[10][1]
    box_h = fh0 * 2.15                                   # head, neck and shoulders
    box_w = box_h * work[0] / work[1]
    cx, cy = lm0[1][0], lm0[10][1] + fh0 * 0.70
    x0, y0 = int(cx - box_w / 2), int(cy - box_h * 0.50)
    img = living.apply_box(src, (x0, y0, int(x0 + box_w), int(y0 + box_h)), work)
    lm, z = _mesh(img)
    face = living.detect(img)
    face.lm = lm
    h, w = img.shape[:2]
    fw = float(np.linalg.norm(lm[454] - lm[234]))
    fh = float(lm[152][1] - lm[10][1])
    alpha = _matte(img)

    # depth: the mesh on the face; behind it, the skull rounds away (hair, ears) to a plane at the back
    back = float(np.median(z) + 0.55 * fw)
    ring = []   # the head's outline: ellipse around the face, set back
    c = lm[1]
    for a in np.linspace(0, 2 * np.pi, 36, endpoint=False):
        ring.append((c[0] + math.cos(a) * fw * 0.80, c[1] - fh * 0.12 + math.sin(a) * fh * 0.95))
    pts = np.vstack([lm[::3], np.array(ring, np.float32)])
    vals = np.concatenate([z[::3], np.full(len(ring), back, np.float32)])
    depth = _smooth_fill((h, w), pts, vals, sigma=fw * 0.10)

    # what moves with the head: everything above the neck; the neck blends into the body
    chin = float(lm[152][1])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ramp = np.clip((chin + 0.55 * fh - yy) / (0.45 * fh), 0, 1)        # 1 above the chin, 0 at the collar
    side = np.clip(1.0 - (np.abs(xx - lm[152][0]) - fw * 0.85) / (fw * 0.6), 0, 1)
    head_w = (ramp * np.where(yy < chin, 1.0, side)).astype(np.float32)
    head_w = cv2.GaussianBlur(head_w, (0, 0), fw * 0.05)
    breath_w = np.clip((yy - chin) / (0.8 * fh), 0, 1).astype(np.float32)   # chest and shoulders rise
    pivot = (float(lm[152][0]), chin + 0.25 * fh, float(np.median(z) + 0.45 * fw))
    rig = Rig(img=img, alpha=alpha, lm=lm, z=z, depth=depth, head_w=head_w, breath_w=breath_w, pivot=pivot,
              face=face, fw=fw, fh=fh)
    rig.extra["eyes"] = [_eye_geometry(img, lm, up, lo) for up, lo in ((L_UP, L_LO), (R_UP, R_LO))]
    return rig


# ---------------------------------------------------------------------------
# eyelids: the lid's skin slides down over the eye (a real blink), with a lash line at its edge
# ---------------------------------------------------------------------------
def _eye_geometry(img: np.ndarray, lm: np.ndarray, up: list[int], lo: list[int]) -> dict:
    U, L = lm[up], lm[lo]
    x0, x1 = float(min(U[:, 0].min(), L[:, 0].min())), float(max(U[:, 0].max(), L[:, 0].max()))
    xs = np.arange(int(x0) - 2, int(x1) + 3)
    u = np.interp(xs, U[:, 0], U[:, 1]) if U[0, 0] < U[-1, 0] else np.interp(xs, U[::-1, 0], U[::-1, 1])
    l = np.interp(xs, L[:, 0], L[:, 1]) if L[0, 0] < L[-1, 0] else np.interp(xs, L[::-1, 0], L[::-1, 1])
    height = float(np.max(l - u))
    return {"xs": xs, "u": u, "l": l, "band": max(4.0, height * 1.6), "h": height}


def blink_eye(out: np.ndarray, eye: dict, c: float) -> None:
    """Closes one eye by c (0 open .. 1 shut) in place: skin from above the lid slides down to the edge."""
    if c <= 0.02:
        return
    xs, u, l, band = eye["xs"], eye["u"], eye["l"], eye["band"]
    edge = u + (l + 0.15 * eye["h"] - u) * c                 # the lid edge comes down past the lower lid line
    h, w = out.shape[:2]
    top = int(max(0, (u - band).min() - 2))
    bot = int(min(h - 1, edge.max() + 3))
    src = out.copy()
    mapx = np.tile(np.arange(w, dtype=np.float32), (bot - top, 1))
    mapy = np.tile(np.arange(top, bot, dtype=np.float32)[:, None], (1, w))
    for i, x in enumerate(xs):
        if not 0 <= x < w:
            continue
        a, e = u[i] - band, edge[i]
        rows = np.arange(top, bot, dtype=np.float32)
        inside = (rows >= a) & (rows <= e)
        # rows between the crease and the new edge sample the lid band (crease .. original lid line), stretched
        t = (rows[inside] - a) / max(1.0, e - a)
        mapy[inside, x] = a + t * (u[i] - a)
    # feather the columns at the eye corners so the lid meets the skin smoothly
    patch = cv2.remap(src, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    mask = np.zeros((bot - top, w), np.float32)
    for i, x in enumerate(xs):
        if 0 <= x < w:
            y0, y1 = int(u[i] - band) - top, int(edge[i] + 1) - top
            mask[max(0, y0):max(0, y1), x] = 1.0
    mask = cv2.GaussianBlur(mask, (0, 0), 1.2)[..., None]
    region = out[top:bot].astype(np.float32)
    region = region * (1 - mask) + patch.astype(np.float32) * mask
    # lash line and the soft shadow it casts: darker where the lid is more closed
    lash = np.zeros((bot - top, w), np.float32)
    pts = np.array([[x, edge[i] - top] for i, x in enumerate(xs)], np.int32)
    cv2.polylines(lash, [pts], False, 1.0, thickness=max(1, int(eye["h"] * 0.10)), lineType=cv2.LINE_AA)
    lash = cv2.GaussianBlur(lash, (0, 0), 1.1) * min(1.0, c * 1.2)
    shade = np.zeros_like(lash)                                       # the lid's soft shadow just above the edge
    cv2.polylines(shade, [pts - np.array([0, int(eye["h"] * 0.25)], np.int32)], False, 1.0,
                  thickness=max(2, int(eye["h"] * 0.35)), lineType=cv2.LINE_AA)
    shade = cv2.GaussianBlur(shade, (0, 0), 2.0) * c
    region *= (1 - 0.35 * lash[..., None]) * (1 - 0.10 * shade[..., None])
    out[top:bot] = np.clip(region, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# small local moves: brows, gaze, smile (backward warp fields on the face)
# ---------------------------------------------------------------------------
def _local_field(rig: Rig, brow: float, gaze: tuple[float, float], smile: float) -> np.ndarray | None:
    lm, mw = rig.lm, rig.face.mouth_w
    shape = rig.img.shape[:2]
    total = None
    if brow > 0.01:
        pts = np.vstack([lm[L_BROW], lm[R_BROW], lm[EYE_RING]])
        dsp = np.vstack([np.tile([0, -brow * rig.fh * 0.035], (len(L_BROW) + len(R_BROW), 1)),
                         np.zeros((len(EYE_RING), 2))]).astype(np.float32)
        total = living._field(shape, pts + dsp, dsp, 0.22 * mw)
    gx, gy = gaze
    if abs(gx) > 0.05 or abs(gy) > 0.05:
        iris = np.vstack([lm[L_IRIS], lm[R_IRIS]])
        pts = np.vstack([iris, lm[EYE_RING]])
        dsp = np.vstack([np.tile([gx, gy], (len(iris), 1)), np.zeros((len(EYE_RING), 2))]).astype(np.float32)
        f = living._field(shape, pts + dsp, dsp, 0.045 * mw, step=2)
        total = f if total is None else total + f
    if smile > 0.01:
        corners = lm[[61, 291]]
        dsp = np.array([[-0.05 * mw * smile, -0.05 * mw * smile], [0.05 * mw * smile, -0.05 * mw * smile]], np.float32)
        anchors = lm[[0, 17, 152, 1]]
        pts = np.vstack([corners, anchors])
        d = np.vstack([dsp, np.zeros((4, 2), np.float32)])
        f = living._field(shape, pts + d, d, 0.35 * mw)
        total = f if total is None else total + f
    return total


# ---------------------------------------------------------------------------
# head pose: a 3D turn of the head layer about the top of the neck
# ---------------------------------------------------------------------------
def _rot(yaw: float, pitch: float, roll: float) -> np.ndarray:
    y, p, r = map(math.radians, (yaw, pitch, roll))
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    rz = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
    return rz @ ry @ rx


def head_map(rig: Rig, yaw: float, pitch: float, roll: float, breath: float) -> tuple[np.ndarray, np.ndarray]:
    """Backward map (where each output pixel comes from) for a head pose and a breath (px)."""
    h, w = rig.img.shape[:2]
    if not hasattr(rig, "_grid"):
        rig._grid = np.mgrid[0:h, 0:w].astype(np.float32)[::-1]   # (x, y)
    gx, gy = rig._grid
    px, py, pz = rig.pivot
    R = _rot(yaw, pitch, roll)
    X, Y, Z = gx - px, gy - py, rig.depth - pz
    nx = R[0, 0] * X + R[0, 1] * Y + R[0, 2] * Z
    ny = R[1, 0] * X + R[1, 1] * Y + R[1, 2] * Z
    dx = ((nx - X) * rig.head_w).astype(np.float32)
    dy = ((ny - Y) * rig.head_w - breath * rig.breath_w - breath * 0.6 * rig.head_w).astype(np.float32)
    # forward displacement -> backward map, refined once (good for these small poses)
    mx, my = gx - dx, gy - dy
    dx2 = cv2.remap(dx, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    dy2 = cv2.remap(dy, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return (gx - dx2).astype(np.float32), (gy - dy2).astype(np.float32)


# ---------------------------------------------------------------------------
# studio backdrop and the camera
# ---------------------------------------------------------------------------
def studio(size: tuple[int, int], seed: int = 3) -> np.ndarray:
    """A dark studio wall with out-of-focus lights: Kenya on Record's red and warm whites."""
    w, h = size
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    top, bottom = np.array([34, 24, 18], np.float32), np.array([20, 14, 11], np.float32)   # BGR, deep charcoal
    bg = top + (bottom - top) * (yy / h)[..., None]
    glow = np.exp(-(((xx - w * 0.5) / (w * 0.45)) ** 2 + ((yy - h * 0.38) / (h * 0.45)) ** 2))
    bg += glow[..., None] * np.array([38, 46, 58], np.float32)                            # warm key behind him
    lights = np.zeros((h, w, 3), np.float32)
    for _ in range(26):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.75)
        r = rng.uniform(w * 0.015, w * 0.045)
        col = np.array([54, 54, 223], np.float32) if rng.random() < 0.35 else np.array([170, 205, 240], np.float32)
        cv2.circle(lights, (int(x), int(y)), int(r), (col * rng.uniform(0.25, 0.6)).tolist(), -1, cv2.LINE_AA)
    lights = cv2.GaussianBlur(lights, (0, 0), w * 0.012)
    return np.clip(bg + lights, 0, 255)


def grade(img: np.ndarray, alpha: np.ndarray, fw: float) -> np.ndarray:
    """The person, matched to the studio: a neutral balance, gentle contrast, a cool rim light on the edge."""
    f = img.astype(np.float32)
    m = alpha[..., None]
    mean = (f * m).reshape(-1, 3).sum(0) / max(1.0, m.sum())
    target = mean.mean()
    gain = np.clip(target / np.maximum(mean, 1), 0.9, 1.12)          # take out the indoor-light cast, gently
    f *= gain
    f = 255 * (0.5 + (f / 255 - 0.5) * 1.06)                        # a little contrast
    edge = np.clip(alpha - cv2.erode(alpha, np.ones((5, 5), np.uint8), iterations=2), 0, 1)
    edge = cv2.GaussianBlur(edge, (0, 0), fw * 0.015)[..., None]
    f += edge * np.array([60, 50, 40], np.float32)                   # rim light
    return np.clip(f, 0, 255)


def camera(img: np.ndarray, t: float, dur: float, rng: np.random.Generator) -> np.ndarray:
    h, w = img.shape[:2]
    s = 1.0 + 0.03 * min(1.0, t / max(dur, 1))                       # slow push-in
    dx = 5 * math.sin(2 * math.pi * t / 7.3) + 2 * math.sin(2 * math.pi * t / 2.9)
    dy = 4 * math.sin(2 * math.pi * t / 6.1)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 0.15 * math.sin(2 * math.pi * t / 9.0), s)
    m[:, 2] += (dx, dy)
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    x0, y0 = (w - OUT_W) // 2, (h - OUT_H) // 2
    out = out[y0:y0 + OUT_H, x0:x0 + OUT_W].astype(np.float32)
    out += rng.normal(0, 2.2, out.shape[:2])[..., None]             # grain
    return np.clip(out, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# the performance: what every part does, frame by frame
# ---------------------------------------------------------------------------
def envelope(wav: Path, n: int) -> np.ndarray:
    """Loudness per frame (0..1)."""
    with wave.open(str(wav)) as wf:
        sr, ch = wf.getframerate(), wf.getnchannels()
        data = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32)
    if ch > 1:
        data = data.reshape(-1, ch).mean(1)
    hop = sr / FPS
    env = np.array([np.sqrt(np.mean(data[int(i * hop):int((i + 1) * hop)] ** 2) + 1e-9) for i in range(n)])
    env = np.convolve(env, np.ones(3) / 3, mode="same")
    return env / max(1e-6, np.percentile(env, 98))


def blink_curve(n: int, env: np.ndarray, rng: random.Random) -> np.ndarray:
    """Real blinks: fast close (~100 ms), slower open (~200 ms), 2-6 s apart, often at a pause, now and then twice."""
    out = np.zeros(n, np.float32)
    shape = [0.35, 0.8, 1.0, 1.0, 0.85, 0.6, 0.35, 0.15, 0.05]
    i = int(rng.uniform(0.6, 1.6) * FPS)
    while i < n - len(shape):
        # prefer a nearby pause (the voice dips): people blink between phrases
        window = range(i, min(n - len(shape), i + int(0.8 * FPS)))
        quiet = [k for k in window if env[k] < 0.15]
        k = quiet[0] if quiet else i
        for j, v in enumerate(shape):
            out[k + j] = max(out[k + j], v)
        if rng.random() < 0.12 and k + 2 * len(shape) < n:          # a double blink
            for j, v in enumerate(shape):
                out[k + len(shape) + j] = max(out[k + len(shape) + j], v * 0.9)
        i = k + int(rng.uniform(2.2, 5.5) * FPS)
    return out


def performance(cues: list[dict], wav: Path, duration: float, seed: int) -> list[dict]:
    n = max(1, round(duration * FPS))
    rng = random.Random(seed)
    env = envelope(wav, n)
    mouth = living.performance(cues, duration, seed)                  # jaw, width, teeth from the visemes
    blinks = blink_curve(n, env, rng)
    # stressed syllables: local peaks of loudness, at least 0.5 s apart
    peaks, last = [], -99
    for i in range(2, n - 2):
        if env[i] > 0.75 and env[i] >= env[i - 2:i + 3].max() and i - last > 0.5 * FPS:
            peaks.append(i)
            last = i
    nod = np.zeros(n)
    brow = np.zeros(n)
    for k, p in enumerate(peaks):
        lift = k % 3 == 0 or rng.random() < 0.2          # brows lift on some stressed words, not all
        for j in range(min(n - p, FPS)):
            t = j / FPS
            nod[p + j] += 1.6 * math.exp(-t / 0.22) * math.sin(math.pi * min(1.0, t / 0.18))
            if lift:
                brow[p + j] = max(brow[p + j], math.exp(-t / 0.35))
    # where he looks: mostly the lens, short glances away and back
    gaze = np.zeros((n, 2))
    i = int(rng.uniform(1.5, 3) * FPS)
    while i < n:
        d = int(rng.uniform(0.25, 0.7) * FPS)
        g = (rng.uniform(-1, 1) * 0.10 * 30, rng.uniform(-0.4, 0.6) * 0.06 * 30)
        for k in range(i, min(n, i + d)):
            gaze[k] = g
        i += d + int(rng.uniform(1.8, 4.5) * FPS)
    gaze = np.array([np.convolve(gaze[:, c], np.ones(3) / 3, mode="same") for c in range(2)]).T
    ph = [rng.uniform(0, 6.28) for _ in range(6)]
    speak = 0.0
    out = []
    for i in range(n):
        t = i / FPS
        speak = 0.95 * speak + 0.05 * (1.0 if env[i] > 0.12 else 0.0)
        yaw = 2.6 * math.sin(2 * math.pi * t / 6.7 + ph[0]) + 1.1 * math.sin(2 * math.pi * t / 2.3 + ph[1]) * speak
        pitch = 1.2 * math.sin(2 * math.pi * t / 5.1 + ph[2]) - nod[i]
        roll = 1.3 * math.sin(2 * math.pi * t / 7.9 + ph[3]) + 0.5 * math.sin(2 * math.pi * t / 3.1 + ph[4]) * speak
        breath = 2.2 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 3.8 + ph[5]))
        smile = max(0.0, min(1.0, (t - (duration - 1.4)) / 0.6))
        jaw, width, teeth, _, _ = mouth[i]
        out.append({"jaw": jaw, "width": width, "teeth": teeth, "blink": float(blinks[i]), "yaw": yaw,
                    "pitch": pitch, "roll": roll, "breath": breath, "brow": float(brow[i]),
                    "gaze": tuple(gaze[i]), "smile": smile})
    return out


# ---------------------------------------------------------------------------
# one frame
# ---------------------------------------------------------------------------
def frame(rig: Rig, p: dict, bg: np.ndarray, t: float, dur: float, rng: np.random.Generator) -> np.ndarray:
    face = rig.face
    living.SHAPES_TEETH["current"] = p["teeth"]
    out = living.frame(face, p["jaw"], p["width"], 0.0)               # mouth (visemes, real interior)
    fld = _local_field(rig, p["brow"], p["gaze"], p["smile"])
    if fld is not None:
        h, w = out.shape[:2]
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        out = cv2.remap(out, (gx - fld[..., 0]).astype(np.float32), (gy - fld[..., 1]).astype(np.float32),
                        cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    for eye in rig.extra["eyes"]:
        blink_eye(out, eye, p["blink"])
    mx, my = head_map(rig, p["yaw"], p["pitch"], p["roll"], p["breath"])
    person = cv2.remap(out, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    alpha = cv2.remap(rig.alpha, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    person = grade(person, alpha, rig.fw)
    comp = bg * (1 - alpha[..., None]) + person * alpha[..., None]
    return camera(comp.astype(np.float32), t, dur, rng)


def talk(portrait: Path, wav: Path, script: str, out: Path, ff: str, seed: int = 0) -> Path:
    """The presenter as an mp4 (OUT_W x OUT_H, no audio), exactly as long as the voice."""
    import presenter
    rig = build(portrait)
    open_photo = portrait.with_name("mouth-open.jpg")
    if open_photo.exists():
        try:
            rig.face.extra["mouth"] = living.mouth_texture(cv2.imread(str(open_photo)))
        except Exception as e:
            print(f"  mouth photo not used: {e}")
    dur = presenter.seconds(wav)
    perf = performance(presenter.cues(wav, script), wav, dur, seed)
    bg = studio((rig.img.shape[1], rig.img.shape[0]), seed=3)
    rng = np.random.default_rng(seed)
    with tempfile.TemporaryDirectory() as t:
        for i, p in enumerate(perf):
            cv2.imwrite(str(Path(t) / f"r{i:05d}.jpg"), frame(rig, p, bg, i / FPS, dur, rng),
                        [cv2.IMWRITE_JPEG_QUALITY, 93])
        subprocess.run([ff, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(Path(t) / "r%05d.jpg"),
                        "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "17", str(out)],
                       check=True)
    return out


def main(argv: list[str]) -> int:
    if len(argv) >= 6 and argv[0] == "talk":
        talk(Path(argv[1]), Path(argv[2]), Path(argv[3]).read_text(encoding="utf-8"), Path(argv[4]), argv[5],
             int(argv[6]) if len(argv) > 6 else 0)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
