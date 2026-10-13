"""
build_logo.py — the Kenyans Are Asking logo set as font-independent SVGs (text converted to outlines).

Mark: "many voices, one question". Three speech bubbles in the flag's black, red and green, separated by the
flag's white bands; the front one carries the question mark. Every Kenyan asking together, in the national
colours only: no single party colour leads, no flag, no shield.
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


BUBBLE_H, TAIL = 0.80, 0.12    # kept for the lockup's spacing maths
MARK_H = 0.92                  # mark ink height as a share of its width
FLAG_BLACK, FLAG_RED, FLAG_GREEN = "#141210", P["shuka"]["600"], P["chai"]["700"]


def _bubble(x: float, y: float, w: float, h: float, r: float, fill: str, gap: str | None, gw: float,
            tail: str = "left") -> str:
    """One rounded speech bubble with its tail; `gap` draws the flag's white band around it."""
    tx = x + w * (0.18 if tail == "left" else 0.62)
    d = (f"M{x + r:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
         f"V{y + h - r:.1f} Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} "
         + (f"H{tx + w * 0.22:.1f} L{tx:.1f},{y + h + w * 0.2:.1f} L{tx:.1f},{y + h:.1f} " if tail == "left" else "")
         + f"H{x + r:.1f} Q{x:.1f},{y + h:.1f} {x:.1f},{y + h - r:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} Z")
    band = f'<path d="{d}" fill="{gap}" stroke="{gap}" stroke-width="{gw:.1f}" stroke-linejoin="round"/>' if gap else ""
    return band + f'<path d="{d}" fill="{fill}"/>'


def mark(x: float, y: float, s: float, bubble: str | None = None, q: str = "#FFFFFF", gap: str = "#FFFFFF",
         colours: tuple[str, str, str] | None = None) -> str:
    """Three bubbles, s wide, top-left at (x, y): red behind on the left, green behind on the right, black in
    front with the white "?". One-colour versions pass `bubble` (all three in one ink, bands in `gap`)."""
    return "".join(mark_parts(x, y, s, bubble, q, gap, colours))


def mark_parts(x: float, y: float, s: float, bubble: str | None = None, q: str = "#FFFFFF", gap: str = "#FFFFFF",
               colours: tuple[str, str, str] | None = None) -> list[str]:
    """The mark as its four pieces (red, green, black, "?"), so the Reel sting can animate each voice."""
    black, red, green = colours or ((bubble,) * 3 if bubble else (FLAG_BLACK, FLAG_RED, FLAG_GREEN))
    bw, bh, r = s * 0.58, s * 0.42, s * 0.11
    gw = s * 0.05
    parts = [_bubble(x, y, bw, bh, r, red, gap, gw, tail="none"),   # the back voices: no tails, no stray slivers
             _bubble(x + s - bw, y, bw, bh, r, green, gap, gw, tail="none")]
    fw, fh = s * 0.66, s * 0.50
    fx, fy = x + (s - fw) / 2, y + s * 0.22
    parts.append(_bubble(fx, fy, fw, fh, s * 0.13, black, gap, gw * 1.4, tail="left"))
    qx0, qend = text_outline("?", fh * 0.62, 0, 0)
    qd, _ = text_outline("?", fh * 0.62, fx + (fw - qend) / 2, fy + fh / 2 + fh * 0.31)
    return parts + [f'<path d="{qd}" fill="{q}"/>']


def sting_svg() -> str:
    """assets/logo/sting.svg: the mark with each piece in its own group (#red #green #black #q) and the wordmark
    (#word), for the animated end card of every Reel (video.py)."""
    s, x, y = 520, 280, 560
    red, green, black, q = mark_parts(x, y, s)
    cx = x + s / 2
    d, end = text_outline("KENYANS ARE ASKING", 60, 0, 0, track=-0.01)
    d, _ = text_outline("KENYANS ARE ASKING", 60, (1080 - end) / 2, y + s * 0.92 + 150, track=-0.01)   # 120px margins
    o = f"transform-origin:{cx:.0f}px {y + s * 0.45:.0f}px"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" width="1080" height="1920">'
            f'<g id="red" style="transform-origin:{x + s * 0.29:.0f}px {y + s * 0.21:.0f}px">{red}</g>'
            f'<g id="green" style="transform-origin:{x + s * 0.71:.0f}px {y + s * 0.21:.0f}px">{green}</g>'
            f'<g id="black" style="{o}">{black}</g><g id="q" style="{o}">{q}</g>'
            f'<g id="word"><path d="{d}" fill="#F8F7F6"/></g></svg>')


def lockup(ink: str, stacked: bool, bg: str | None = None, mono: bool = False, q: str = "#FFFFFF") -> str:
    cap, pad = 100, 24
    bubble = ink if mono else None
    gap = "#FFFFFF"   # the flag's white bands: they also outline the black bubble on dark backgrounds
    if stacked:
        s = 210
        m = mark(pad, pad, s, bubble, q, gap)
        top = pad + s * MARK_H + 46
        d1, e1 = text_outline("KENYANS", cap, pad, top + cap, track=-0.01)
        d2, e2 = text_outline("ARE ASKING", cap, pad, top + 2 * cap + 30, track=-0.01)
        w, h, d = max(e1, e2, pad + s) + pad, top + 2 * cap + 30 + pad, d1 + d2
    else:
        s = cap / MARK_H * 1.55     # the bubbles a little taller than the capitals, tail hanging below the line
        m = mark(pad, pad - cap * 0.22, s, bubble, q, gap)
        d, end = text_outline("KENYANS ARE ASKING", cap, pad + s + 30, pad + cap, track=-0.01)
        w, h = end + pad, cap + 2 * pad + cap * 0.45
    bg_el = f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<title>Kenyans Are Asking</title>{bg_el}{m}<path d="{d}" fill="{ink}"/></svg>')


def icon(bg: str, gap: str | None = None, **kw) -> str:
    """Profile picture / app icon: the mark alone, centred on a flat field (survives a circle crop)."""
    s = 136
    x, y = (200 - s) / 2, (200 - s * 0.82) / 2   # optical centre: bubbles plus the front tail
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="512" height="512">'
            f'<title>Kenyans Are Asking icon</title><rect width="200" height="200" fill="{bg}"/>'
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
    (OUT / "icon-night.svg").write_text(icon(NIGHT, gap="#FFFFFF"), encoding="utf-8")
    (OUT / "icon-red.svg").write_text(icon("#FFFFFF"), encoding="utf-8")   # kept for old references: same as paper
    (OUT / "sting.svg").write_text(sting_svg(), encoding="utf-8")
    print("logo set written to", OUT)


if __name__ == "__main__":
    main()
