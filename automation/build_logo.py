"""
build_logo.py — the Kenya on Record logo set as font-independent SVGs (text converted to outlines).

Mark: a record, a sheet with a folded corner, in the flag's black, with a tick (verified) and the flag's red and
green bands, with their white edges, across it. Kenya on Record: what leaders promised and did, and what Kenya
builds, checked and kept on record.
Wordmark: KENYA ON RECORD in Inter Tight Black, cap height matched to the mark.

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


MARK_H = 1.0                  # mark ink height as a share of its width (the sheet is as tall as it is wide)
FLAG_BLACK, FLAG_RED, FLAG_GREEN = "#141210", P["shuka"]["600"], P["chai"]["700"]


def _sheet(x: float, y: float, w: float, h: float, fill: str) -> str:
    """A record sheet: rounded corners, the top-right corner folded."""
    r, f = w * 0.08, w * 0.22
    d = (f"M{x + r:.1f},{y:.1f} H{x + w - f:.1f} L{x + w:.1f},{y + f:.1f} V{y + h - r:.1f} "
         f"Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x + r:.1f} Q{x:.1f},{y + h:.1f} {x:.1f},{y + h - r:.1f} "
         f"V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} Z")
    return f'<path d="{d}" fill="{fill}"/>'


def mark(x: float, y: float, s: float, bubble: str | None = None, q: str = "#FFFFFF", gap: str = "#FFFFFF",
         colours: tuple[str, str, str] | None = None) -> str:
    """The record, s wide, top-left at (x, y). One-colour versions pass `bubble` (all in one ink)."""
    red, green, body, tick = mark_parts(x, y, s, bubble, q, gap, colours)
    return body + red + green + tick   # the sheet first, the flag bands and the tick on it


def mark_parts(x: float, y: float, s: float, bubble: str | None = None, q: str = "#FFFFFF", gap: str = "#FFFFFF",
               colours: tuple[str, str, str] | None = None) -> list[str]:
    """The mark as four pieces (red band, green band, sheet, tick), so the Reel sting can animate them.
    Kenya's flag in miniature: black, then red and green with the white bands between them."""
    black, red, green = colours or ((bubble,) * 3 if bubble else (FLAG_BLACK, FLAG_RED, FLAG_GREEN))
    w, h = s * 0.8, s * MARK_H
    rx = x + (s - w) / 2
    body = _sheet(rx, y, w, h, black)
    band, white = h * 0.085, h * 0.03
    y1 = y + h * 0.66
    stripe = lambda yy, col: (f'<rect x="{rx:.1f}" y="{yy:.1f}" width="{w:.1f}" height="{band:.1f}" fill="{col}"/>')
    red_el = stripe(y1 - white, gap) + stripe(y1, red)                    # white edge, then red
    green_el = stripe(y1 + band, gap) + stripe(y1 + band + white, green)   # white edge, then green
    pts = [(rx + w * 0.24, y + h * 0.36), (rx + w * 0.43, y + h * 0.53), (rx + w * 0.76, y + h * 0.2)]
    tick = (f'<path d="M{pts[0][0]:.1f},{pts[0][1]:.1f} L{pts[1][0]:.1f},{pts[1][1]:.1f} L{pts[2][0]:.1f},{pts[2][1]:.1f}" '
            f'fill="none" stroke="{q}" stroke-width="{w * 0.12:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
    return [red_el, green_el, body, tick]


def sting_svg() -> str:
    """assets/logo/sting.svg: the mark with each piece in its own group (#red #green #black #q) and the wordmark
    (#word), for the animated end card of every Reel (video.py)."""
    s, x, y = 520, 280, 560
    red, green, black, q = mark_parts(x, y, s, q=NIGHT, colours=ON_DARK)   # paper sheet: the end card is dark
    cx = x + s / 2
    d, end = text_outline("KENYA ON RECORD", 60, 0, 0, track=-0.01)
    d, _ = text_outline("KENYA ON RECORD", 60, (1080 - end) / 2, y + s * 0.92 + 150, track=-0.01)   # 120px margins
    o = f"transform-origin:{cx:.0f}px {y + s * 0.45:.0f}px"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" width="1080" height="1920">'
            f'<g id="black" style="{o}">{black}</g>'
            f'<g id="red" style="transform-origin:{cx:.0f}px {y + s * 0.6:.0f}px">{red}</g>'
            f'<g id="green" style="transform-origin:{cx:.0f}px {y + s * 0.68:.0f}px">{green}</g>'
            f'<g id="q" style="{o}">{q}</g>'
            f'<g id="word"><path d="{d}" fill="#F8F7F6"/></g></svg>')


ON_DARK = (PAPER, FLAG_RED, FLAG_GREEN)   # on a dark field the sheet is paper, the tick ink


def lockup(ink: str, stacked: bool, bg: str | None = None, mono: bool = False, q: str = "#FFFFFF") -> str:
    cap, pad = 100, 24
    bubble = ink if mono else None
    gap = "#FFFFFF"   # the flag's white bands between black, red and green
    colours = ON_DARK if (ink == PAPER and not mono) else None
    if colours:
        q = NIGHT
    if stacked:
        s = 210
        m = mark(pad, pad, s, bubble, q, gap, colours)
        top = pad + s * MARK_H + 46
        d1, e1 = text_outline("KENYA", cap, pad, top + cap, track=-0.01)
        d2, e2 = text_outline("ON RECORD", cap, pad, top + 2 * cap + 30, track=-0.01)
        w, h, d = max(e1, e2, pad + s) + pad, top + 2 * cap + 30 + pad, d1 + d2
    else:
        s = cap / MARK_H * 1.45     # the sheet a little taller than the capitals
        m = mark(pad, pad - cap * 0.22, s, bubble, q, gap, colours)
        d, end = text_outline("KENYA ON RECORD", cap, pad + s + 30, pad + cap, track=-0.01)
        w, h = end + pad, cap + 2 * pad + cap * 0.45
    bg_el = f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<title>Kenya on Record</title>{bg_el}{m}<path d="{d}" fill="{ink}"/></svg>')


def icon(bg: str, gap: str | None = None, **kw) -> str:
    """Profile picture / app icon: the mark alone, centred on a flat field (survives a circle crop)."""
    s = 136
    x, y = (200 - s) / 2, (200 - s * MARK_H) / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="512" height="512">'
            f'<title>Kenya on Record icon</title><rect width="200" height="200" fill="{bg}"/>'
            f'{mark(x, y, s, gap=gap or bg, **kw)}</svg>')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in [*OUT.glob("icon-*.svg"), *OUT.glob("*-mono-*.svg")]:
        old.unlink()
    for name, ink in {"on-light": P["ink"]["900"], "on-dark": PAPER}.items():
        (OUT / f"wordmark-{name}.svg").write_text(lockup(ink, stacked=False), encoding="utf-8")
        (OUT / f"stacked-{name}.svg").write_text(lockup(ink, stacked=True), encoding="utf-8")
    # one-colour versions for red and green backgrounds (the red sun would vanish on red)
    # one-colour versions for red and green backgrounds: a white bubble, the "?" cut in the background colour
    for name, ink, q, bg in (("mono-light", "#FFFFFF", SUN, SUN), ("mono-dark", NIGHT, "#FFFFFF", "#FFFFFF")):
        (OUT / f"wordmark-{name}.svg").write_text(lockup(ink, stacked=False, mono=True, q=q).replace(
            'fill="#FFFFFF" stroke="#FFFFFF"', f'fill="{bg}" stroke="{bg}"'), encoding="utf-8")
        (OUT / f"stacked-{name}.svg").write_text(lockup(ink, stacked=True, mono=True, q=q).replace(
            'fill="#FFFFFF" stroke="#FFFFFF"', f'fill="{bg}" stroke="{bg}"'), encoding="utf-8")
    # the profile picture: white field, so the flag colours and white bands read at any size
    (OUT / "icon-paper.svg").write_text(icon("#FFFFFF"), encoding="utf-8")
    (OUT / "icon-night.svg").write_text(icon(NIGHT, gap=PAPER, colours=ON_DARK, q=NIGHT), encoding="utf-8")
    (OUT / "icon-red.svg").write_text(icon("#FFFFFF"), encoding="utf-8")   # kept for old references: same as paper
    (OUT / "sting.svg").write_text(sting_svg(), encoding="utf-8")
    print("logo set written to", OUT)


if __name__ == "__main__":
    main()
