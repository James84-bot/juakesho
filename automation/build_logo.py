"""
build_logo.py — outputs the Jua Kesho logo set as font-independent SVGs.

The wordmark is "jua kesho" in Unbounded ExtraBold, converted to outlines.
The dot of the j is replaced by a small sun: yellow core, rays in the accent
colours. Run: python build_logo.py
"""
from __future__ import annotations

import math
from pathlib import Path

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from brandkit import C, blob, mascot

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logo"
FONT = ROOT / "assets" / "fonts" / "unbounded-latin-wght-normal.woff2"

font = instancer.instantiateVariableFont(TTFont(FONT), {"wght": 800})
glyphs = font.getGlyphSet()
cmap = font.getBestCmap()
hmtx = font["hmtx"]
UPM = font["head"].unitsPerEm
X_HEIGHT = font["OS/2"].sxHeight or 540


def _split_contours(rec) -> list[list]:
    contours, cur = [], []
    for op, args in rec.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(cur)
            cur = []
    return contours


def _contour_top(contour) -> float:
    ys = [pt[1] for _, args in contour for pt in args if isinstance(pt, tuple)]
    return max(ys) if ys else 0


def text_outline(text: str, size: float, x: float, baseline: float, track: float = -0.02):
    """Returns (path_data, dot_centre_or_None, end_x). The j's dot is removed and its centre returned."""
    scale = size / UPM
    pen = SVGPathPen(glyphs)
    dot_centre = None
    for ch in text:
        name = cmap[ord(ch)]
        rec = DecomposingRecordingPen(glyphs)
        glyphs[name].draw(rec)
        contours = _split_contours(rec)
        if ch == "j":
            dot = max(contours, key=_contour_top)
            contours = [c for c in contours if c is not dot]
            pts = [pt for _, args in dot for pt in args if isinstance(pt, tuple)]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            dot_centre = (x + cx * scale, baseline - cy * scale)
        tp = TransformPen(pen, (scale, 0, 0, -scale, x, baseline))
        for contour in contours:
            for op, args in contour:
                getattr(tp, op)(*args)
        x += hmtx[name][0] * scale + track * size
    return pen.getCommands(), dot_centre, x


def mini_sun(cx: float, cy: float, r: float, seed: int = 7) -> str:
    """The j-dot sun: yellow core plus six short rays."""
    colors = ["shuka", "jacaranda", "chai", "ziwa", "waridi", "pwani"]
    rays = []
    for i, name in enumerate(colors):
        a = 2 * math.pi * i / len(colors) - math.pi / 2
        rays.append(blob(cx + math.cos(a) * r * 1.55, cy + math.sin(a) * r * 1.55, r * 0.42,
                         C[name], seed + i, wobble=0.15, points=5, stretch=1.4, rotate=a))
    return "".join(rays) + blob(cx, cy, r, C["jua"], seed, wobble=0.08, points=8)


def lockup(text_color: str, bg: str | None, stacked: bool) -> str:
    size = 100
    if stacked:
        d1, dot, e1 = text_outline("jua", size, 20, 150)
        d2, _, e2 = text_outline("kesho", size, 20, 262)
        w, h, d = max(e1, e2) + 24, 300, d1 + d2
    else:
        d, dot, end = text_outline("jua kesho", size, 20, 150)
        w, h = end + 24, 200
    bg_el = f'<rect width="{w:.0f}" height="{h}" fill="{bg}"/>' if bg else ""
    sun = mini_sun(dot[0], dot[1] - 10, 20)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h}" width="{w:.0f}" height="{h}">'
            f'<title>Jua Kesho</title>{bg_el}<path d="{d}" fill="{text_color}"/>{sun}</svg>')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    variants = {
        "on-light": (C["usiku"], None),
        "on-dark": (C["maziwa"], None),
    }
    for name, (ink, bg) in variants.items():
        (OUT / f"wordmark-{name}.svg").write_text(lockup(ink, bg, stacked=False), encoding="utf-8")
        (OUT / f"stacked-{name}.svg").write_text(lockup(ink, bg, stacked=True), encoding="utf-8")
    # Icon tiles: Jua on a colour field
    for bg_name in ("jacaranda", "usiku", "maziwa", "pwani"):
        (OUT / f"icon-{bg_name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="512" height="512">'
            f'<title>Jua Kesho icon</title><rect width="200" height="200" fill="{C[bg_name]}"/>'
            f'{mascot("happy")}</svg>', encoding="utf-8")
    print("logo set written to", OUT)


if __name__ == "__main__":
    main()
