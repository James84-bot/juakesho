"""
brandkit.py — Jua Kesho visual primitives.

Everything visual that is generated (irregular shapes, the Jua mascot, the logo)
comes from here, so the site, posts and profile images stay consistent.
All functions return SVG markup strings. Randomness is always seeded, so the
same post renders the same way every time.
"""
from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRAND = json.loads((ROOT / "brand.json").read_text(encoding="utf-8"))
C = {k: v["hex"] for k, v in BRAND["colors"].items()}
ON = {k: v["text"] for k, v in BRAND["colors"].items()}
ACCENTS = BRAND["accents"]


# ---------------------------------------------------------------------------
# Irregular shapes
# ---------------------------------------------------------------------------
def _smooth_closed(points: list[tuple[float, float]], tension: float = 1.0) -> str:
    """Catmull-Rom through closed points -> cubic Bezier path data."""
    n = len(points)
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(n):
        p0, p1, p2, p3 = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6 * tension, p1[1] + (p2[1] - p0[1]) / 6 * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6 * tension, p2[1] - (p3[1] - p1[1]) / 6 * tension)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d + "Z"


def blob_path(cx: float, cy: float, r: float, seed: int, wobble: float = 0.22,
              points: int = 7, stretch: float = 1.0, rotate: float = 0.0) -> str:
    """An organic pebble: a circle whose radius wanders per vertex."""
    rnd = random.Random(seed)
    pts = []
    for i in range(points):
        a = 2 * math.pi * i / points + rnd.uniform(-0.25, 0.25)
        rr = r * (1 + rnd.uniform(-wobble, wobble))
        x, y = math.cos(a) * rr * stretch, math.sin(a) * rr
        ca, sa = math.cos(rotate), math.sin(rotate)
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return _smooth_closed(pts)


def blob(cx, cy, r, fill, seed, **kw) -> str:
    return f'<path d="{blob_path(cx, cy, r, seed, **kw)}" fill="{fill}"/>'


def blob_outline(cx, cy, r, color, seed, width=5, dx=16, dy=18, **kw) -> str:
    """The same blob as blob(cx, cy, r, seed) drawn as an offset outline, like a misregistered print."""
    return (f'<path d="{blob_path(cx, cy, r, seed, **kw)}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" transform="translate({dx} {dy})"/>')


def squiggle(x, y, length, color, seed, amp=14, waves=4, width=10) -> str:
    """A hand-drawn wavy line."""
    rnd = random.Random(seed)
    step = length / (waves * 2)
    d = f"M{x:.1f},{y:.1f}"
    for i in range(waves * 2):
        cx = x + step * (i + 0.5)
        cy = y + (amp if i % 2 == 0 else -amp) * rnd.uniform(0.7, 1.2)
        d += f" Q{cx:.1f},{cy:.1f} {x + step * (i + 1):.1f},{y:.1f}"
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def kanga_band(x, y, w, h, colors: list[str], seed: int) -> str:
    """A border of alternating triangles, the kind printed along kanga and kitenge edges."""
    rnd = random.Random(seed)
    n = max(4, int(w // h))
    tw = w / n
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{colors[0]}"/>']
    for i in range(n):
        c = colors[1 + i % (len(colors) - 1)]
        jitter = rnd.uniform(-0.08, 0.08) * h
        tx = x + i * tw
        out.append(f'<path d="M{tx:.1f},{y + h:.1f} L{tx + tw / 2:.1f},{y + jitter:.1f} '
                   f'L{tx + tw:.1f},{y + h:.1f}Z" fill="{c}"/>')
    return "".join(out)


def dots(x, y, w, h, color, seed, n=18, rmin=4, rmax=9) -> str:
    rnd = random.Random(seed)
    return "".join(
        f'<circle cx="{x + rnd.random() * w:.1f}" cy="{y + rnd.random() * h:.1f}" '
        f'r="{rnd.uniform(rmin, rmax):.1f}" fill="{color}"/>'
        for _ in range(n)
    )


def leaf(cx, cy, size, color, angle, seed) -> str:
    """A tea-leaf shape with a slightly uneven midrib."""
    rnd = random.Random(seed)
    s = size
    bend = rnd.uniform(-0.15, 0.15) * s
    d = (f"M0,{-s:.1f} C{s * 0.55:.1f},{-s * 0.5:.1f} {s * 0.5:.1f},{s * 0.5:.1f} 0,{s:.1f} "
         f"C{-s * 0.5:.1f},{s * 0.5:.1f} {-s * 0.55:.1f},{-s * 0.5:.1f} 0,{-s:.1f}Z")
    rib = f"M0,{-s * 0.8:.1f} Q{bend:.1f},0 0,{s * 0.85:.1f}"
    return (f'<g transform="translate({cx:.1f} {cy:.1f}) rotate({angle:.1f})">'
            f'<path d="{d}" fill="{color}"/>'
            f'<path d="{rib}" stroke="{C["maziwa"]}" stroke-opacity=".55" stroke-width="{max(2, s * 0.06):.1f}" '
            f'fill="none" stroke-linecap="round"/></g>')


def confetti(w, h, seed, n=10, avoid=None, palette=None, rmin=14, rmax=46, footer=150) -> str:
    """Scattered small blobs. `avoid` = one (x, y, w, h) box or a list of them, kept clear
    for text. The bottom `footer` px (logo + handle) is always kept clear."""
    boxes = [] if avoid is None else ([avoid] if isinstance(avoid[0], (int, float)) else list(avoid))
    if footer:
        boxes.append((0, h - footer, w, footer))
    rnd = random.Random(seed)
    palette = palette or [C[a] for a in ACCENTS] + [C["jua"]]
    out, tries = [], 0
    while len(out) < n and tries < n * 30:
        tries += 1
        r = rnd.uniform(rmin, rmax)
        x, y = rnd.uniform(r, w - r), rnd.uniform(r, h - r)
        if any(ax - r < x < ax + aw + r and ay - r < y < ay + ah + r for ax, ay, aw, ah in boxes):
            continue
        out.append(blob(x, y, r, rnd.choice(palette), rnd.randint(0, 10**6), wobble=0.3, points=6))
    return "".join(out)


# ---------------------------------------------------------------------------
# Kesho Mode — the futuristic layer (used on Usiku / night designs)
# Tradition + tomorrow: kanga triangles become circuits, the sun gets orbits.
# ---------------------------------------------------------------------------
GLOW_DEFS = ('<defs><filter id="glow" x="-50%" y="-50%" width="200%" height="200%">'
             '<feGaussianBlur stdDeviation="6" result="b"/>'
             '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')


def orbit(cx, cy, rx, ry, rotate, color, seed, planets=2, width=3, dash=None) -> str:
    """A tilted orbit ring with small planets riding on it."""
    rnd = random.Random(seed)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    out = [f'<g transform="translate({cx} {cy}) rotate({rotate})">'
           f'<ellipse rx="{rx}" ry="{ry}" fill="none" stroke="{color}" stroke-width="{width}" opacity=".85"{dash_attr}/>']
    palette = [C[a] for a in ("jua", "pwani", "waridi", "ziwa")]
    for _ in range(planets):
        a = rnd.uniform(0, 2 * math.pi)
        out.append(f'<circle cx="{math.cos(a) * rx:.1f}" cy="{math.sin(a) * ry:.1f}" '
                   f'r="{rnd.uniform(7, 14):.1f}" fill="{rnd.choice(palette)}" filter="url(#glow)"/>')
    out.append("</g>")
    return "".join(out)


def circuit(x, y, w, h, color, seed, traces=7, width=3) -> str:
    """Circuit-board traces: right-angle paths that end in solder pads."""
    rnd = random.Random(seed)
    out = []
    for _ in range(traces):
        px, py = x + rnd.random() * w, y + rnd.random() * h
        d = f"M{px:.0f},{py:.0f}"
        for step in range(rnd.randint(2, 4)):
            if step % 2 == 0:
                px = min(x + w, max(x, px + rnd.choice([-1, 1]) * rnd.uniform(40, 180)))
            else:
                py = min(y + h, max(y, py + rnd.choice([-1, 1]) * rnd.uniform(30, 120)))
            d += f" L{px:.0f},{py:.0f}"
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
                   f'stroke-linejoin="round" opacity=".55"/>'
                   f'<circle cx="{px:.0f}" cy="{py:.0f}" r="{width * 2.4:.1f}" fill="none" '
                   f'stroke="{color}" stroke-width="{width}" opacity=".8"/>')
    return "".join(out)


def circuit_kanga(x, y, w, h, colors: list[str], seed: int) -> str:
    """The kanga border reimagined: outlined triangles joined by a trace line."""
    n = max(4, int(w // h))
    tw = w / n
    out = [f'<path d="M{x},{y + h} H{x + w}" stroke="{colors[0]}" stroke-width="3"/>']
    for i in range(n):
        tx = x + i * tw
        c = colors[i % len(colors)]
        out.append(f'<path d="M{tx + 4:.1f},{y + h:.1f} L{tx + tw / 2:.1f},{y + 4:.1f} L{tx + tw - 4:.1f},{y + h:.1f}" '
                   f'fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>'
                   f'<circle cx="{tx + tw / 2:.1f}" cy="{y + 4:.1f}" r="4" fill="{c}"/>')
    return "".join(out)


def pixel_sun(cx, cy, r, cell=14, seed=0) -> str:
    """A sun made of LED dots: dense yellow core, coloured dots at the edge."""
    rnd = random.Random(seed)
    edge = [C[a] for a in ("shuka", "jacaranda", "pwani", "waridi", "ziwa")]
    out = []
    steps = int(r * 1.5 // cell)
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            x, y = cx + i * cell, cy + j * cell
            d = math.hypot(x - cx, y - cy)
            if d <= r * 0.72:
                out.append(f'<circle cx="{x}" cy="{y}" r="{cell * 0.38:.1f}" fill="{C["jua"]}"/>')
            elif d <= r * 1.35 and rnd.random() < 0.3 * (1.35 - d / r) / 0.63:
                out.append(f'<circle cx="{x}" cy="{y}" r="{cell * 0.3:.1f}" fill="{rnd.choice(edge)}"/>')
    return "".join(out)


def aurora(w, h, seed, colors=None, blur=90, n=5) -> str:
    """Big soft colour clouds for Glass mode: frosted cards float over these."""
    rnd = random.Random(seed)
    colors = colors or [C["jacaranda"], C["pwani"], C["waridi"], C["jua"], C["ziwa"]]
    fid = f"au{seed}"
    blobs = "".join(
        blob(rnd.uniform(0, w), rnd.uniform(0, h), rnd.uniform(0.22, 0.42) * max(w, h), colors[i % len(colors)],
             seed + i * 13, wobble=0.3, points=6)
        for i in range(n))
    return (f'<defs><filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%">'
            f'<feGaussianBlur stdDeviation="{blur}"/></filter></defs>'
            f'<g class="aurora" filter="url(#{fid})" opacity=".85">{blobs}</g>')


# ---------------------------------------------------------------------------
# Jua — the mascot
# A sun with rays in every accent colour: one light, many people.
# ---------------------------------------------------------------------------
EXPRESSIONS = ("happy", "wow", "wink", "thinking", "cool", "laugh", "visor")


def _eyes(expr: str) -> str:
    ink = C["usiku"]
    L, R = (78, 96), (122, 96)
    if expr == "wink":
        return (f'<ellipse cx="{L[0]}" cy="{L[1]}" rx="7.5" ry="10" fill="{ink}"/>'
                f'<circle cx="{L[0] + 2.5}" cy="{L[1] - 3.5}" r="2.6" fill="#fff"/>'
                f'<path d="M{R[0] - 9},{R[1] + 1} Q{R[0]},{R[1] - 8} {R[0] + 9},{R[1] + 1}" '
                f'fill="none" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>')
    if expr == "laugh":
        return "".join(
            f'<path d="M{x - 9},{y + 2} Q{x},{y - 9} {x + 9},{y + 2}" fill="none" stroke="{ink}" '
            f'stroke-width="5" stroke-linecap="round"/>' for x, y in (L, R))
    if expr == "visor":
        # Kesho Mode: a wraparound visor with a scan line
        return (f'<path d="M50,84 Q100,72 150,84 L148,106 Q100,116 52,106Z" fill="{ink}"/>'
                f'<path d="M58,90 Q100,80 142,90 L141,100 Q100,109 59,100Z" fill="{C["pwani"]}" opacity=".9"/>'
                f'<path d="M62,95 Q100,86 138,95" stroke="#fff" stroke-width="2.5" fill="none" opacity=".9"/>'
                f'<circle cx="80" cy="95" r="3.5" fill="{C["jua"]}"/><circle cx="120" cy="95" r="3.5" fill="{C["jua"]}"/>')
    if expr == "cool":
        return (f'<path d="M56,86 H144 V92 Q144,110 124,110 Q106,110 104,94 H96 Q94,110 76,110 '
                f'Q56,110 56,92Z" fill="{ink}"/>'
                f'<path d="M66,92 L78,92" stroke="#fff" stroke-opacity=".7" stroke-width="3" stroke-linecap="round"/>'
                f'<path d="M114,92 L126,92" stroke="#fff" stroke-opacity=".7" stroke-width="3" stroke-linecap="round"/>')
    big = expr == "wow"
    rx, ry = (9, 12.5) if big else (7.5, 10)
    look = (3, -3) if expr == "thinking" else (0, 0)
    out = ""
    for x, y in (L, R):
        out += (f'<ellipse cx="{x + look[0]}" cy="{y + look[1]}" rx="{rx}" ry="{ry}" fill="{ink}"/>'
                f'<circle cx="{x + look[0] + 2.5}" cy="{y + look[1] - 3.5}" r="2.8" fill="#fff"/>')
    if expr == "thinking":
        out += (f'<path d="M66,{L[1] - 20} Q78,{L[1] - 26} 88,{L[1] - 21}" fill="none" stroke="{ink}" '
                f'stroke-width="4" stroke-linecap="round"/>')
    return out


def _mouth(expr: str) -> str:
    ink = C["usiku"]
    if expr == "wow":
        return f'<ellipse cx="100" cy="128" rx="10" ry="12" fill="{ink}"/><ellipse cx="100" cy="133" rx="6" ry="4" fill="{C["shuka"]}"/>'
    if expr == "thinking":
        return f'<path d="M90,128 Q100,124 112,127" fill="none" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>'
    if expr == "laugh":
        return (f'<path d="M78,118 Q100,150 122,118 Z" fill="{ink}"/>'
                f'<path d="M88,131 Q100,141 112,131 Q100,136 88,131Z" fill="{C["shuka"]}"/>')
    if expr in ("cool", "visor"):
        return f'<path d="M86,124 Q102,138 118,122" fill="none" stroke="{ink}" stroke-width="5" stroke-linecap="round"/>'
    return f'<path d="M82,120 Q100,142 118,120" fill="none" stroke="{ink}" stroke-width="5.5" stroke-linecap="round"/>'


def mascot(expr: str = "happy", face: bool = True, seed: int = 2026) -> str:
    """Jua as an SVG group in a 200x200 box (no <svg> wrapper)."""
    rnd = random.Random(seed)
    rays = []
    ray_colors = ["shuka", "jacaranda", "chai", "ziwa", "waridi", "pwani", "udongo", "shuka", "jacaranda", "chai"]
    n = 10
    for i in range(n):
        a = 2 * math.pi * i / n - math.pi / 2 + rnd.uniform(-0.08, 0.08)
        dist = 84 + rnd.uniform(-3, 5)
        size = 12 + rnd.uniform(-2, 4)
        x, y = 100 + math.cos(a) * dist, 104 + math.sin(a) * dist
        rays.append(blob(x, y, size, C[ray_colors[i]], seed + i * 17, wobble=0.18, points=5,
                         stretch=1.5, rotate=a))
    body = blob(100, 104, 66, C["jua"], seed, wobble=0.07, points=9)
    shade = (f'<path d="{blob_path(108, 112, 58, seed + 3, wobble=0.07, points=9)}" '
             f'fill="#F2A71B" opacity=".35"/>')
    highlight = (f'<path d="{blob_path(78, 72, 16, seed + 5, wobble=0.2, points=6, stretch=1.6, rotate=-0.6)}" '
                 f'fill="#fff" opacity=".45"/>')
    parts = ["".join(rays), body, shade, blob(100, 104, 60, C["jua"], seed + 1, wobble=0.06, points=9), highlight]
    if face:
        parts.append(f'<ellipse cx="66" cy="120" rx="10" ry="6.5" fill="{C["waridi"]}" opacity=".7"/>'
                     f'<ellipse cx="134" cy="120" rx="10" ry="6.5" fill="{C["waridi"]}" opacity=".7"/>')
        parts.append(_eyes(expr))
        parts.append(_mouth(expr))
    # Scale to keep the rays inside the 200x200 box, centred on the body
    return f'<g transform="translate(100 100) scale(0.84) translate(-100 -104)">{"".join(parts)}</g>'


def mascot_svg(expr="happy", size=400, face=True, bg: str | None = None) -> str:
    bg_el = f'<rect width="200" height="200" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="{size}" height="{size}">'
            f'<title>Jua, the Jua Kesho mascot</title>{bg_el}{mascot(expr, face)}</svg>')


def font_faces(font_dir: str) -> str:
    """@font-face rules for the three brand fonts (variable WOFF2)."""
    return (
        f'@font-face{{font-family:"Unbounded";src:url("{font_dir}/unbounded-latin-wght-normal.woff2") format("woff2");font-weight:200 900}}'
        f'@font-face{{font-family:"Figtree";src:url("{font_dir}/figtree-latin-wght-normal.woff2") format("woff2");font-weight:300 900}}'
        f'@font-face{{font-family:"Caveat";src:url("{font_dir}/caveat-latin-wght-normal.woff2") format("woff2");font-weight:400 700}}'
    )


# ---------------------------------------------------------------------------
# Stick cast — faceless-friendly people for scenes and comics.
# One skeleton (forward kinematics) + poses + props per character, so every
# figure has the same proportions and line weight everywhere.
# Angles are degrees measured from "straight down"; positive swings to the
# viewer's right. 180 = straight up.
# ---------------------------------------------------------------------------
BONES = {"torso": 56, "neck": 8, "head": 17, "upper_arm": 33, "fore_arm": 31, "thigh": 47, "shin": 46}
LINE = 9

POSES = {
    #          lean   L arm (upper, fore)   R arm (upper, fore)   L leg (thigh, shin)  R leg (thigh, shin)  head tilt
    "stand":  (0,    (-24, -10),            (24, 10),             (-10, -4),           (10, 4),             0),
    "wave":   (-4,   (-24, -10),            (135, 168),           (-10, -4),           (10, 4),             -6),
    "point":  (3,    (-24, -10),            (96, 92),             (-10, -3),           (11, 5),             4),
    "think":  (0,    (-26, 30),             (150, 250),           (-9, -3),            (10, 4),             8),
    "cheer":  (0,    (-148, -168),          (148, 168),           (-16, -4),           (16, 4),             0),
    "walk":   (4,    (22, 8),               (-24, -42),           (-24, -4),           (22, 38),            3),
    "phone":  (-3,   (-24, -10),            (30, 160),            (-10, -3),           (10, 4),             8),
    "shrug":  (0,    (-46, -128),           (46, 128),            (-10, -4),           (10, 4),             -8),
    "sit":    (-6,   (-20, 60),             (20, -60),            (-80, -8),           (-72, 2),            0),
}

CAST = {
    "shosh":      {"label": "Shosh", "who": "Grandma. Curious and sharp; asks the questions everyone is shy to ask."},
    "makanga":    {"label": "Makanga", "who": "Matatu conductor. Street-smart; explains tech through routes and stages."},
    "mama_mboga": {"label": "Mama Mboga", "who": "Runs the vegetable stall. Practical and quick with M-Pesa."},
    "boda":       {"label": "Boda", "who": "Boda boda rider. Always on the move; loves shortcuts and data savings."},
    "student":    {"label": "Mwanafunzi", "who": "Student and job seeker. Learning skills online."},
    "pro":        {"label": "Boss", "who": "Professional. Uses AI at work; learns that the stage has wisdom too."},
    "farmer":     {"label": "Mkulima", "who": "Farmer. Weather apps, market prices and farm advice by phone."},
    "creator":    {"label": "Creator", "who": "Posts daily, knows every trend. Wants tools that save editing time."},
    "techie":     {"label": "Techie", "who": "Hoodie, laptop, builds things. The friend who explains how it works."},
    "ahadi":      {"label": "Bwana Ahadi", "who": "Mr Promise. A fictional archetype of anyone who promises big and delivers little. Never drawn to resemble a real person."},
}


def _step(p, angle, length):
    a = math.radians(angle)
    return (p[0] + math.sin(a) * length, p[1] + math.cos(a) * length)


def skeleton(x: float, ground: float, pose: str = "stand", scale: float = 1.0) -> dict:
    """Joint positions for a figure whose feet stand on `ground`."""
    lean, la, ra, ll, rl, tilt = POSES[pose]
    b = {k: v * scale for k, v in BONES.items()}
    # Build from the hip, then shift so the lowest foot touches the ground.
    hip = (0.0, 0.0)
    j = {"hip": hip}
    j["neck_base"] = _step(hip, 180 + lean, b["torso"])
    j["shoulder"] = _step(hip, 180 + lean, b["torso"] * 0.9)
    j["head"] = _step(j["neck_base"], 180 + lean + tilt, b["neck"] + b["head"])
    for side, (up, fore) in (("l", la), ("r", ra)):
        j[f"{side}_elbow"] = _step(j["shoulder"], up, b["upper_arm"])
        j[f"{side}_hand"] = _step(j[f"{side}_elbow"], fore, b["fore_arm"])
    for side, (th, sh) in (("l", ll), ("r", rl)):
        j[f"{side}_knee"] = _step(hip, th, b["thigh"])
        j[f"{side}_foot"] = _step(j[f"{side}_knee"], sh, b["shin"])
    lowest = max(j["l_foot"][1], j["r_foot"][1])
    if pose == "sit":
        lowest = j["hip"][1] + b["shin"] * 0.15  # sitting on something at hip height
    dx, dy = x, ground - lowest
    j = {k: (v[0] + dx, v[1] + dy) for k, v in j.items()}
    j["tilt"], j["lean"], j["scale"], j["head_r"] = tilt, lean, scale, b["head"]
    return j


def _limb(a, b, c, ink, w) -> str:
    """Two bones with a softly rounded joint, so limbs bend like limbs."""
    return (f'<path d="M{a[0]:.1f},{a[1]:.1f} Q{b[0]:.1f},{b[1]:.1f} {c[0]:.1f},{c[1]:.1f}" fill="none" stroke="{ink}" '
            f'stroke-width="{w:.1f}" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="M{a[0]:.1f},{a[1]:.1f} L{b[0]:.1f},{b[1]:.1f} L{c[0]:.1f},{c[1]:.1f}" fill="none" stroke="{ink}" '
            f'stroke-width="{w:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')


def _face(j, mood: str, ink: str) -> str:
    hx, hy = j["head"]
    s = j["scale"]
    r = j["head_r"]
    ex, ey = 5.5 * s, -2 * s
    eyes = "".join(f'<circle cx="{hx + dx:.1f}" cy="{hy + ey:.1f}" r="{2.3 * s:.1f}" fill="{ink}"/>' for dx in (-ex, ex))
    my = hy + 7 * s
    mouths = {
        "happy": f'<path d="M{hx - 5 * s:.1f},{my - 1 * s:.1f} Q{hx:.1f},{my + 5 * s:.1f} {hx + 5 * s:.1f},{my - 1 * s:.1f}" fill="none" stroke="{ink}" stroke-width="{2.4 * s:.1f}" stroke-linecap="round"/>',
        "worried": f'<path d="M{hx - 5 * s:.1f},{my + 2 * s:.1f} Q{hx:.1f},{my - 3 * s:.1f} {hx + 5 * s:.1f},{my + 2 * s:.1f}" fill="none" stroke="{ink}" stroke-width="{2.4 * s:.1f}" stroke-linecap="round"/>',
        "wow": f'<ellipse cx="{hx:.1f}" cy="{my + 1 * s:.1f}" rx="{3 * s:.1f}" ry="{4 * s:.1f}" fill="{ink}"/>',
        "flat": f'<path d="M{hx - 4 * s:.1f},{my:.1f} H{hx + 4 * s:.1f}" stroke="{ink}" stroke-width="{2.4 * s:.1f}" stroke-linecap="round"/>',
    }
    return (f'<g transform="rotate({j["tilt"] + j["lean"]} {hx:.1f} {hy:.1f})">'
            f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{r:.1f}" fill="{C["maziwa"]}" stroke="{ink}" stroke-width="{LINE * s * 0.8:.1f}"/>'
            f'{eyes}{mouths.get(mood, mouths["happy"])}</g>')


def _outline(svg: str, width: float) -> str:
    """Give filled prop shapes a dark outline so clothing never vanishes into a same-colour background."""
    ink = C["usiku"]
    return re.sub(r'<(path|rect|ellipse)((?:(?!stroke=)[^>])*?fill="(?!none)[^"]+")((?:(?!stroke=)[^>])*)/>',
                  lambda m: f'<{m.group(1)}{m.group(2)}{m.group(3)} stroke="{ink}" stroke-width="{width:.1f}" stroke-linejoin="round"/>',
                  svg)


def _props_back(who: str, j: dict) -> str:
    """Drawn behind the body."""
    s = j["scale"]
    if who == "student":  # backpack
        sx, sy = j["shoulder"]
        return f'<rect x="{sx - 20 * s:.1f}" y="{sy - 2 * s:.1f}" width="{26 * s:.1f}" height="{40 * s:.1f}" rx="{8 * s:.1f}" fill="{C["ziwa"]}"/>'
    if who == "shosh":  # kanga wrap skirt
        hx, hy = j["hip"]
        nx, ny = j["neck_base"]
        top = hy - (hy - ny) * 0.35
        return (f'<path d="M{hx - 12 * s:.1f},{top:.1f} L{hx + 12 * s:.1f},{top:.1f} L{hx + 27 * s:.1f},{hy + 40 * s:.1f} '
                f'Q{hx:.1f},{hy + 46 * s:.1f} {hx - 27 * s:.1f},{hy + 40 * s:.1f}Z" fill="{C["jacaranda"]}"/>'
                + dots(hx - 18 * s, top + 10 * s, 36 * s, 30 * s, C["jua"], 5, n=6, rmin=2.5 * s, rmax=3.5 * s))
    return ""


def _props_front(who: str, j: dict) -> str:
    s = j["scale"]
    hx, hy = j["head"]
    r = j["head_r"]
    rot = f'rotate({j["tilt"] + j["lean"]} {hx:.1f} {hy:.1f})'
    out = ""
    if who == "shosh":
        out += (f'<g transform="{rot}"><path d="{blob_path(hx, hy - r * 0.75, r * 1.05, 21, wobble=0.12, points=7, stretch=1.25)}" fill="{C["shuka"]}"/>'
                f'{blob(hx + r * 1.0, hy - r * 1.2, r * 0.42, C["shuka"], 22, wobble=0.2, points=5)}'
                f'<circle cx="{hx - 5.5 * s:.1f}" cy="{hy - 2 * s:.1f}" r="{5 * s:.1f}" fill="none" stroke="{C["usiku"]}" stroke-width="{1.8 * s:.1f}"/>'
                f'<circle cx="{hx + 5.5 * s:.1f}" cy="{hy - 2 * s:.1f}" r="{5 * s:.1f}" fill="none" stroke="{C["usiku"]}" stroke-width="{1.8 * s:.1f}"/></g>')
        lx, ly = j["l_hand"]  # walking stick
        out += f'<path d="M{lx:.1f},{ly - 6 * s:.1f} L{lx - 4 * s:.1f},{max(j["l_foot"][1], j["r_foot"][1]):.1f}" stroke="{C["udongo"]}" stroke-width="{5 * s:.1f}" stroke-linecap="round"/>'
    elif who == "makanga":
        out += (f'<g transform="{rot}"><path d="M{hx - r:.1f},{hy - r * 0.25:.1f} A{r:.1f},{r:.1f} 0 0 1 {hx + r:.1f},{hy - r * 0.25:.1f}Z" fill="{C["usiku"]}"/>'
                f'<path d="M{hx + r * 0.2:.1f},{hy - r * 0.3:.1f} H{hx + r * 1.8:.1f}" stroke="{C["usiku"]}" stroke-width="{5 * s:.1f}" stroke-linecap="round"/></g>')
        px, py = j["hip"]
        out += f'<rect x="{px + 4 * s:.1f}" y="{py - 12 * s:.1f}" width="{16 * s:.1f}" height="{14 * s:.1f}" rx="{4 * s:.1f}" fill="{C["jua"]}"/>'
    elif who == "mama_mboga":
        out += (f'<g transform="{rot}"><path d="{blob_path(hx, hy - r * 0.8, r * 0.95, 31, wobble=0.1, points=6, stretch=1.2)}" fill="{C["chai"]}"/></g>')
        nx, ny = j["neck_base"]
        px, py = j["hip"]
        out += (f'<path d="M{nx - 10 * s:.1f},{ny + 14 * s:.1f} L{nx + 10 * s:.1f},{ny + 14 * s:.1f} L{px + 16 * s:.1f},{py + 16 * s:.1f} L{px - 16 * s:.1f},{py + 16 * s:.1f}Z" fill="{C["waridi"]}"/>')
        lx, ly = j["l_hand"]  # kiondo basket
        out += (f'<path d="M{lx - 16 * s:.1f},{ly + 2 * s:.1f} Q{lx:.1f},{ly - 16 * s:.1f} {lx + 16 * s:.1f},{ly + 2 * s:.1f}" fill="none" stroke="{C["udongo"]}" stroke-width="{3 * s:.1f}"/>'
                f'<path d="M{lx - 17 * s:.1f},{ly:.1f} H{lx + 17 * s:.1f} L{lx + 12 * s:.1f},{ly + 20 * s:.1f} H{lx - 12 * s:.1f}Z" fill="{C["udongo"]}"/>'
                f'<circle cx="{lx - 6 * s:.1f}" cy="{ly - 3 * s:.1f}" r="{5 * s:.1f}" fill="{C["shuka"]}"/><circle cx="{lx + 5 * s:.1f}" cy="{ly - 4 * s:.1f}" r="{5 * s:.1f}" fill="{C["chai"]}"/>')
    elif who == "boda":
        out += (f'<g transform="{rot}"><path d="M{hx - r * 1.15:.1f},{hy + r * 0.2:.1f} A{r * 1.15:.1f},{r * 1.2:.1f} 0 0 1 {hx + r * 1.15:.1f},{hy + r * 0.2:.1f}Z" fill="{C["shuka"]}"/>'
                f'<path d="M{hx - r * 0.2:.1f},{hy - r * 0.2:.1f} H{hx + r * 1.15:.1f} V{hy + r * 0.25:.1f} H{hx - r * 0.2:.1f}Z" fill="{C["usiku"]}" opacity=".85"/></g>')
        nx, ny = j["neck_base"]
        px, py = j["hip"]
        out += (f'<path d="M{nx - 13 * s:.1f},{ny + 8 * s:.1f} L{nx + 13 * s:.1f},{ny + 8 * s:.1f} L{px + 13 * s:.1f},{py:.1f} L{px - 13 * s:.1f},{py:.1f}Z" fill="{C["jua"]}"/>'
                f'<path d="M{px - 13 * s:.1f},{(ny + py) / 2 + 6 * s:.1f} H{px + 13 * s:.1f}" stroke="{C["maziwa"]}" stroke-width="{3.5 * s:.1f}"/>')
    elif who == "student":
        rx_, ry_ = j["l_hand"]
        out += f'<rect x="{rx_ - 9 * s:.1f}" y="{ry_ - 14 * s:.1f}" width="{18 * s:.1f}" height="{22 * s:.1f}" rx="{2 * s:.1f}" fill="{C["shuka"]}" transform="rotate(-12 {rx_:.1f} {ry_:.1f})"/>'
    elif who == "pro":
        nx, ny = j["neck_base"]
        out += (f'<path d="M{nx:.1f},{ny + 4 * s:.1f} L{nx - 5 * s:.1f},{ny + 12 * s:.1f} L{nx:.1f},{ny + 36 * s:.1f} L{nx + 5 * s:.1f},{ny + 12 * s:.1f}Z" fill="{C["jacaranda"]}"/>')
        lx, ly = j["l_hand"]
        out += (f'<rect x="{lx - 22 * s:.1f}" y="{ly - 3 * s:.1f}" width="{30 * s:.1f}" height="{20 * s:.1f}" rx="{3 * s:.1f}" fill="{C["usiku"]}"/>'
                f'<circle cx="{lx - 7 * s:.1f}" cy="{ly + 7 * s:.1f}" r="{3 * s:.1f}" fill="{C["maziwa"]}"/>')
    elif who == "creator":
        out += (f'<g transform="{rot}"><path d="M{hx - r:.1f},{hy - r * 0.2:.1f} A{r:.1f},{r:.1f} 0 0 1 {hx + r:.1f},{hy - r * 0.2:.1f}Z" fill="{C["waridi"]}"/>'
                f'<path d="M{hx - r * 1.7:.1f},{hy - r * 0.3:.1f} H{hx - r * 0.3:.1f}" stroke="{C["waridi"]}" stroke-width="{5 * s:.1f}" stroke-linecap="round"/></g>')
        lx, ly = j["l_hand"]  # ring light on a stick
        out += (f'<path d="M{lx:.1f},{ly:.1f} L{lx - 10 * s:.1f},{ly - 50 * s:.1f}" stroke="{C["usiku"]}" stroke-width="{3 * s:.1f}" stroke-linecap="round"/>'
                f'<circle cx="{lx - 12 * s:.1f}" cy="{ly - 62 * s:.1f}" r="{12 * s:.1f}" fill="none" stroke="{C["jua"]}" stroke-width="{5 * s:.1f}"/>')
    elif who == "techie":
        out += (f'<g transform="{rot}"><path d="M{hx - r * 1.25:.1f},{hy + r * 0.9:.1f} Q{hx - r * 1.45:.1f},{hy - r * 1.5:.1f} {hx:.1f},{hy - r * 1.35:.1f} '
                f'Q{hx + r * 1.45:.1f},{hy - r * 1.5:.1f} {hx + r * 1.25:.1f},{hy + r * 0.9:.1f}" fill="none" stroke="{C["jacaranda"]}" stroke-width="{7 * s:.1f}" stroke-linecap="round"/></g>')
        nx, ny = j["neck_base"]
        px, py = j["hip"]
        out += f'<path d="M{nx - 15 * s:.1f},{ny + 6 * s:.1f} L{nx + 15 * s:.1f},{ny + 6 * s:.1f} L{px + 16 * s:.1f},{py + 4 * s:.1f} L{px - 16 * s:.1f},{py + 4 * s:.1f}Z" fill="{C["jacaranda"]}"/>'
        rx_, ry_ = j["r_hand"]
        out += (f'<path d="M{rx_ - 4 * s:.1f},{ry_ - 2 * s:.1f} L{rx_ + 26 * s:.1f},{ry_ - 2 * s:.1f} L{rx_ + 22 * s:.1f},{ry_ + 16 * s:.1f} L{rx_:.1f},{ry_ + 16 * s:.1f}Z" fill="{C["usiku"]}"/>'
                f'<circle cx="{rx_ + 11 * s:.1f}" cy="{ry_ + 7 * s:.1f}" r="{2.5 * s:.1f}" fill="{C["pwani"]}"/>')
    elif who == "ahadi":
        nx, ny = j["neck_base"]
        px, py = j["hip"]
        out += (f'<path d="M{nx - 16 * s:.1f},{ny + 4 * s:.1f} L{nx + 16 * s:.1f},{ny + 4 * s:.1f} L{px + 19 * s:.1f},{py + 6 * s:.1f} L{px - 19 * s:.1f},{py + 6 * s:.1f}Z" fill="{C["usiku"]}"/>'
                f'<path d="M{nx:.1f},{ny + 6 * s:.1f} L{nx - 5 * s:.1f},{ny + 14 * s:.1f} L{nx:.1f},{ny + 38 * s:.1f} L{nx + 5 * s:.1f},{ny + 14 * s:.1f}Z" fill="{C["jua"]}"/>')
        rx_, ry_ = j["r_hand"]  # megaphone
        out += (f'<path d="M{rx_:.1f},{ry_ - 5 * s:.1f} L{rx_ + 26 * s:.1f},{ry_ - 16 * s:.1f} L{rx_ + 26 * s:.1f},{ry_ + 14 * s:.1f} L{rx_:.1f},{ry_ + 5 * s:.1f}Z" fill="{C["shuka"]}"/>'
                + "".join(f'<path d="M{rx_ + 32 * s:.1f},{ry_ + d * s:.1f} q{6 * s:.1f},0 {10 * s:.1f},{d * 0.5 * s:.1f}" fill="none" stroke="{C["shuka"]}" stroke-width="{2.5 * s:.1f}" stroke-linecap="round"/>' for d in (-10, 0, 10)))
    elif who == "farmer":
        out += (f'<g transform="{rot}"><ellipse cx="{hx:.1f}" cy="{hy - r * 0.55:.1f}" rx="{r * 2:.1f}" ry="{r * 0.35:.1f}" fill="{C["udongo"]}"/>'
                f'<path d="M{hx - r * 0.9:.1f},{hy - r * 0.6:.1f} Q{hx:.1f},{hy - r * 2:.1f} {hx + r * 0.9:.1f},{hy - r * 0.6:.1f}Z" fill="{C["udongo"]}"/></g>')
        rx_, ry_ = j["r_hand"]  # jembe
        out += (f'<path d="M{rx_:.1f},{ry_ - 30 * s:.1f} L{rx_:.1f},{ry_ + 34 * s:.1f}" stroke="{C["udongo"]}" stroke-width="{4.5 * s:.1f}" stroke-linecap="round"/>'
                f'<path d="M{rx_ - 3 * s:.1f},{ry_ + 30 * s:.1f} L{rx_ + 16 * s:.1f},{ry_ + 32 * s:.1f} L{rx_ + 14 * s:.1f},{ry_ + 42 * s:.1f} L{rx_ - 3 * s:.1f},{ry_ + 38 * s:.1f}Z" fill="{C["ziwa"]}"/>')
    return out


def phone_in_hand(j: dict, side: str = "r", lit: bool = True) -> str:
    x, y = j[f"{side}_hand"]
    s = j["scale"]
    screen = C["pwani"] if lit else C["maziwa"]
    return (f'<g transform="rotate(-10 {x:.1f} {y:.1f})"><rect x="{x - 8 * s:.1f}" y="{y - 26 * s:.1f}" width="{16 * s:.1f}" height="{28 * s:.1f}" rx="{3 * s:.1f}" fill="{C["usiku"]}"/>'
            f'<rect x="{x - 5.5 * s:.1f}" y="{y - 23 * s:.1f}" width="{11 * s:.1f}" height="{20 * s:.1f}" rx="{1.5 * s:.1f}" fill="{screen}"/></g>')


def stick(who: str, x: float, ground: float, pose: str = "stand", mood: str = "happy",
          scale: float = 1.0, phone: bool = False, ink: str | None = None) -> str:
    """A cast member standing on `ground` at horizontal position `x`."""
    ink = ink or C["usiku"]
    j = skeleton(x, ground, pose, scale)
    w = LINE * scale
    ow = 2.6 * scale
    body = [_outline(_props_back(who, j), ow) if who != "shosh" else ""]
    body.append(_limb(j["hip"], j["l_knee"], j["l_foot"], ink, w))
    body.append(_limb(j["hip"], j["r_knee"], j["r_foot"], ink, w))
    for side, d in (("l", -1), ("r", 1)):  # small feet, toes turned slightly out
        fx, fy = j[f"{side}_foot"]
        body.append(f'<path d="M{fx:.1f},{fy:.1f} L{fx + d * 10 * scale:.1f},{fy + 1 * scale:.1f}" stroke="{ink}" '
                    f'stroke-width="{w:.1f}" stroke-linecap="round"/>')
    if who == "shosh":
        body.append(_outline(_props_back(who, j), ow))  # the kanga covers the legs
    body.append(f'<path d="M{j["hip"][0]:.1f},{j["hip"][1]:.1f} L{j["neck_base"][0]:.1f},{j["neck_base"][1]:.1f}" stroke="{ink}" stroke-width="{w:.1f}" stroke-linecap="round"/>')
    body.append(_limb(j["shoulder"], j["l_elbow"], j["l_hand"], ink, w))
    body.append(_limb(j["shoulder"], j["r_elbow"], j["r_hand"], ink, w))
    body.append(_face(j, mood, ink))
    body.append(_outline(_props_front(who, j), ow))
    if phone:
        body.append(phone_in_hand(j, "r"))
    shadow = f'<ellipse cx="{x:.1f}" cy="{ground + 3 * scale:.1f}" rx="{30 * scale:.1f}" ry="{5 * scale:.1f}" fill="{C["usiku"]}" opacity=".15"/>'
    return shadow + "".join(body)


def head_of(pose: str, x: float, ground: float, scale: float = 1.0) -> tuple[float, float]:
    """Where a figure's head will be; used to aim speech-bubble tails."""
    return skeleton(x, ground, pose, scale)["head"]
