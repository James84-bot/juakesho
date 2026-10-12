"""
build_logo.py — the Kenyans Are Asking logo set as font-independent SVGs (text converted to outlines).

Mark: a speech bubble with a question mark: Kenyans asking. Flag red bubble, white "?", a green rule under the
wordmark's first line in the stacked version. Flag colours, no flag, no shield.
Wordmark: KENYANS ARE ASKING in Inter Tight Black, cap height matched to the mark.

    python build_logo.py      # writes assets/logo/*.svg
"""
from __future__ import annotations

from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from brandkit import P

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logo"
FONT = ROOT / "assets" / "fonts" / "inter-tight-latin-wght-normal.woff2"

SUN, HORIZON = P["shuka"]["600"], P["chai"]["600"]
NIGHT, PAPER = P["ink"]["950"], P["ink"]["50"]

font = instancer.instantiateVariableFont(TTFont(FONT), {"wght": 900})
glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
UPM = font["head"].unitsPerEm
CAP = font["OS/2"].sCapHeight or 0.727 * UPM


KERN = {"WA": -0.06, "YA": -0.075, "AY": -0.06, "AV": -0.05, "LT": -0.05}   # outlines skip the font's kerning: the pairs that need it


def text_outline(text: str, cap_px: float, x: float, baseline: float, track: float = 0.0) -> tuple[str, float]:
    """Outlines `text` so its capitals are `cap_px` tall. Returns (path data, end x)."""
    size = cap_px * UPM / CAP
    scale = size / UPM
    pen = SVGPathPen(glyphs)
    for i, ch in enumerate(text):
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += hmtx[name][0] * scale + (track + KERN.get(text[i:i + 2], 0.0)) * size
    return pen.getCommands(), x


BUBBLE_H, TAIL = 0.80, 0.20    # bubble body height and tail depth (shares of the mark's width)
MARK_H = BUBBLE_H + TAIL       # mark ink height as a share of its width


def mark(x: float, y: float, s: float, bubble: str = SUN, q: str = "#FFFFFF") -> str:
    """A speech bubble (s wide, top-left at (x, y)) with a bold question mark inside, tail at the lower left."""
    h, r = s * BUBBLE_H, s * 0.2
    tail = (f'<path d="M{x + s * .16:.1f},{y + h - 1:.1f} L{x + s * .16:.1f},{y + h + s * TAIL:.1f} '
            f'L{x + s * .44:.1f},{y + h - 1:.1f} Z" fill="{bubble}"/>')
    qd, qend = text_outline("?", s * 0.52, 0, 0)
    qw = qend
    qx, qy = x + (s - qw) / 2, y + h / 2 + s * 0.26
    qd, _ = text_outline("?", s * 0.52, qx, qy)
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{s:.1f}" height="{h:.1f}" rx="{r:.1f}" fill="{bubble}"/>{tail}'
            f'<path d="{qd}" fill="{q}"/>')


def lockup(ink: str, stacked: bool, bg: str | None = None, mono: bool = False, q: str = "#FFFFFF") -> str:
    cap, pad = 100, 24
    bubble = ink if mono else SUN
    if stacked:
        s = 210
        m = mark(pad, pad, s, bubble, q)
        top = pad + s * MARK_H + 46
        d1, e1 = text_outline("KENYANS", cap, pad, top + cap, track=-0.01)
        d2, e2 = text_outline("ARE ASKING", cap, pad, top + 2 * cap + 30, track=-0.01)
        w, h, d = max(e1, e2, pad + s) + pad, top + 2 * cap + 30 + pad, d1 + d2
    else:
        s = cap / MARK_H * 1.25     # the bubble a little taller than the capitals, tail hanging below the line
        m = mark(pad, pad - cap * 0.12, s, bubble, q)
        d, end = text_outline("KENYANS ARE ASKING", cap, pad + s + 28, pad + cap, track=-0.01)
        w, h = end + pad, cap + 2 * pad + cap * 0.25
    bg_el = f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<title>Kenyans Are Asking</title>{bg_el}{m}<path d="{d}" fill="{ink}"/></svg>')


def icon(bg: str, bubble: str, q: str) -> str:
    """Profile picture / app icon: the mark alone, centred on a flat field (survives a circle crop)."""
    s = 128
    x, y = (200 - s) / 2, (200 - s * MARK_H) / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="512" height="512">'
            f'<title>Kenyans Are Asking icon</title><rect width="200" height="200" fill="{bg}"/>{mark(x, y, s, bubble, q)}</svg>')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in [*OUT.glob("icon-*.svg"), *OUT.glob("*-mono-*.svg")]:
        old.unlink()
    for name, ink in {"on-light": P["ink"]["900"], "on-dark": PAPER}.items():
        (OUT / f"wordmark-{name}.svg").write_text(lockup(ink, stacked=False), encoding="utf-8")
        (OUT / f"stacked-{name}.svg").write_text(lockup(ink, stacked=True), encoding="utf-8")
    # one-colour versions for red and green backgrounds (the red sun would vanish on red)
    # one-colour versions for red and green backgrounds: a white bubble, the "?" cut in the background colour
    for name, ink, q in (("mono-light", "#FFFFFF", SUN), ("mono-dark", NIGHT, "#FFFFFF")):
        (OUT / f"wordmark-{name}.svg").write_text(lockup(ink, stacked=False, mono=True, q=q), encoding="utf-8")
        (OUT / f"stacked-{name}.svg").write_text(lockup(ink, stacked=True, mono=True, q=q), encoding="utf-8")
    (OUT / "icon-night.svg").write_text(icon(NIGHT, SUN, "#FFFFFF"), encoding="utf-8")
    (OUT / "icon-paper.svg").write_text(icon(PAPER, SUN, "#FFFFFF"), encoding="utf-8")
    (OUT / "icon-red.svg").write_text(icon(SUN, "#FFFFFF", SUN), encoding="utf-8")
    print("logo set written to", OUT)


if __name__ == "__main__":
    main()
