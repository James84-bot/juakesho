"""
build_logo.py — the Jua Kesho logo set as font-independent SVGs (text converted to outlines).

Mark: the sun rising over the horizon: a red half disc over a green line. Flag colours, no flag, no shield
(the national flag and emblems themselves are protected; their colours are free to use).
Wordmark: JUA KESHO in Inter Tight Black, cap height matched to the mark.

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


def text_outline(text: str, cap_px: float, x: float, baseline: float, track: float = 0.0) -> tuple[str, float]:
    """Outlines `text` so its capitals are `cap_px` tall. Returns (path data, end x)."""
    size = cap_px * UPM / CAP
    scale = size / UPM
    pen = SVGPathPen(glyphs)
    for ch in text:
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += hmtx[name][0] * scale + track * size
    return pen.getCommands(), x


R, GAP, LINE = 0.34, 0.07, 0.09   # disc radius, gap, horizon thickness (shares of the mark's width)
MARK_H = R + GAP + LINE           # mark ink height as a share of its width


def mark(x: float, y: float, s: float, sun: str = SUN, horizon_c: str | None = None) -> str:
    """Sun rising over a horizon that runs wider than the sun: s wide, top-left at (x, y)."""
    r, cx = s * R, x + s / 2
    horizon = y + r
    return (f'<path d="M{cx - r:.1f},{horizon:.1f} A{r:.1f},{r:.1f} 0 0 1 {cx + r:.1f},{horizon:.1f} Z" fill="{sun}"/>'
            f'<rect x="{x:.1f}" y="{horizon + s * GAP:.1f}" width="{s:.1f}" height="{s * LINE:.1f}" fill="{horizon_c or (HORIZON if sun == SUN else sun)}"/>')


def lockup(ink: str, stacked: bool, bg: str | None = None, mono: bool = False) -> str:
    cap, pad = 100, 24
    if stacked:
        s = 230
        m = mark(pad, pad, s, *((ink, ink) if mono else ()))
        top = pad + s * MARK_H + 46
        d1, e1 = text_outline("JUA", cap, pad, top + cap, track=-0.01)
        d2, e2 = text_outline("KESHO", cap, pad, top + 2 * cap + 30, track=-0.01)
        w, h, d = max(e1, e2, pad + s) + pad, top + 2 * cap + 30 + pad, d1 + d2
    else:
        s = cap / MARK_H          # the mark's ink is exactly cap height
        m = mark(pad, pad, s, *((ink, ink) if mono else ()))
        d, end = text_outline("JUA KESHO", cap, pad + s + 30, pad + cap, track=-0.01)
        w, h = end + pad, cap + 2 * pad
    bg_el = f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<title>Jua Kesho</title>{bg_el}{m}<path d="{d}" fill="{ink}"/></svg>')


def icon(bg: str, fg: str | None = None) -> str:
    """Profile picture / app icon: the mark alone, centred on a flat field (survives a circle crop)."""
    s = 136
    x, y = (200 - s) / 2, (200 - s * MARK_H) / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="512" height="512">'
            f'<title>Jua Kesho icon</title><rect width="200" height="200" fill="{bg}"/>{mark(x, y, s, *((fg, fg) if fg else ()))}</svg>')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in [*OUT.glob("icon-*.svg"), *OUT.glob("*-mono-*.svg")]:
        old.unlink()
    for name, ink in {"on-light": P["ink"]["900"], "on-dark": PAPER}.items():
        (OUT / f"wordmark-{name}.svg").write_text(lockup(ink, stacked=False), encoding="utf-8")
        (OUT / f"stacked-{name}.svg").write_text(lockup(ink, stacked=True), encoding="utf-8")
    # one-colour versions for red and green backgrounds (the red sun would vanish on red)
    for name, ink in {"mono-light": "#FFFFFF", "mono-dark": NIGHT}.items():
        (OUT / f"wordmark-{name}.svg").write_text(lockup(ink, stacked=False, mono=True), encoding="utf-8")
        (OUT / f"stacked-{name}.svg").write_text(lockup(ink, stacked=True, mono=True), encoding="utf-8")
    (OUT / "icon-night.svg").write_text(icon(NIGHT), encoding="utf-8")
    (OUT / "icon-paper.svg").write_text(icon(PAPER), encoding="utf-8")
    (OUT / "icon-red.svg").write_text(icon(SUN, "#FFFFFF"), encoding="utf-8")
    print("logo set written to", OUT)


if __name__ == "__main__":
    main()
