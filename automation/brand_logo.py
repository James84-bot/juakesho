"""
brand_logo.py — the logo set of a brand other than Kenya on Record, in the same family: a dark shape crossed by the
Kenyan flag's red and green bands (with their white edges) and a white symbol, then the name in Inter Tight Black.
Each brand has its own shape, so the five read as one network and still apart at a glance:

    scoreboard  Full Time Kenya      a rounded scoreboard, "FT" on it
    coin        Shilling Brief       a coin, "Sh" on it
    shield      Verified Jobs Kenya  a badge, a tick on it
    stamp       Kenya Postcards      a postage stamp, Mount Kenya's peak on it

Mtaa Mode (logo "style": "street") is not part of the news family: a lime chat bubble with three typing dots and the
name in Unbounded, its own look (street comedy should neither borrow nor dent the news brands' credibility).

brand.json "logo": {"shape": ..., "symbol": ..., "lines": ["FULL TIME", "KENYA"]}. Writes brands/<slug>/logo/ with the
same file names render.py and video.py read for Kenya on Record (wordmark-*, stacked-*, icon-*, sting.svg).

    KOR_BRAND=fulltimekenya python brand_logo.py
"""
from __future__ import annotations

import brands
from build_logo import FLAG_BLACK, FLAG_GREEN, FLAG_RED, NIGHT, PAPER, P, text_outline

SUN = P["shuka"]["600"]


def _shape(kind: str, x: float, y: float, w: float, h: float) -> str:
    """The shape's outline as path data, inside the box (x, y, w, h)."""
    if kind == "coin":
        r = min(w, h) / 2
        cx, cy = x + w / 2, y + h / 2
        return (f"M{cx - r:.1f},{cy:.1f} A{r:.1f},{r:.1f} 0 1,0 {cx + r:.1f},{cy:.1f} "
                f"A{r:.1f},{r:.1f} 0 1,0 {cx - r:.1f},{cy:.1f} Z")
    if kind == "shield":
        return (f"M{x + w / 2:.1f},{y:.1f} L{x + w:.1f},{y + h * 0.14:.1f} V{y + h * 0.5:.1f} "
                f"Q{x + w:.1f},{y + h * 0.82:.1f} {x + w / 2:.1f},{y + h:.1f} "
                f"Q{x:.1f},{y + h * 0.82:.1f} {x:.1f},{y + h * 0.5:.1f} V{y + h * 0.14:.1f} Z")
    if kind == "stamp":   # perforated edge: small bites along every side
        n, r = 7, w * 0.035
        d = f"M{x:.1f},{y:.1f} "
        for side in range(4):
            for i in range(n):
                t0, t1 = i / n, (i + 1) / n
                tm = (t0 + t1) / 2
                if side == 0:
                    a, m, b = (x + w * t0, y), (x + w * tm, y), (x + w * t1, y)
                elif side == 1:
                    a, m, b = (x + w, y + h * t0), (x + w, y + h * tm), (x + w, y + h * t1)
                elif side == 2:
                    a, m, b = (x + w * (1 - t0), y + h), (x + w * (1 - tm), y + h), (x + w * (1 - t1), y + h)
                else:
                    a, m, b = (x, y + h * (1 - t0)), (x, y + h * (1 - tm)), (x, y + h * (1 - t1))
                d += (f"L{m[0] - (b[0] - a[0]) * 0.18:.1f},{m[1] - (b[1] - a[1]) * 0.18:.1f} "
                      f"A{r:.1f},{r:.1f} 0 0,0 {m[0] + (b[0] - a[0]) * 0.18:.1f},{m[1] + (b[1] - a[1]) * 0.18:.1f} "
                      f"L{b[0]:.1f},{b[1]:.1f} ")
        return d + "Z"
    r = w * 0.16   # scoreboard: a rounded rectangle
    return (f"M{x + r:.1f},{y:.1f} H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h - r:.1f} "
            f"Q{x + w:.1f},{y + h:.1f} {x + w - r:.1f},{y + h:.1f} H{x + r:.1f} Q{x:.1f},{y + h:.1f} {x:.1f},{y + h - r:.1f} "
            f"V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} Z")


def _symbol(sym: str, x: float, y: float, w: float, h: float, ink: str) -> str:
    """The white sign in the upper half of the shape: two letters, a tick or a peak."""
    if sym == "tick":
        pts = [(x + w * 0.3, y + h * 0.36), (x + w * 0.45, y + h * 0.5), (x + w * 0.72, y + h * 0.22)]
        return (f'<path d="M{pts[0][0]:.1f},{pts[0][1]:.1f} L{pts[1][0]:.1f},{pts[1][1]:.1f} L{pts[2][0]:.1f},{pts[2][1]:.1f}" '
                f'fill="none" stroke="{ink}" stroke-width="{w * 0.11:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
    if sym == "peak":   # Mount Kenya: Batian and Nelion, the jagged twin summit, as one white shape
        bx = lambda u: x + w * u
        by = lambda v: y + h * v
        pts = [(0.16, 0.56), (0.36, 0.33), (0.41, 0.37), (0.5, 0.16), (0.555, 0.25), (0.6, 0.21), (0.84, 0.56)]
        d = "M" + " L".join(f"{bx(u):.1f},{by(v):.1f}" for u, v in pts) + " Z"
        return f'<path d="{d}" fill="{ink}" stroke="{ink}" stroke-width="{w * 0.02:.1f}" stroke-linejoin="round"/>'
    cap = h * 0.26   # letters
    d, end = text_outline(sym, cap, 0, 0, track=-0.02)
    d, _ = text_outline(sym, cap, x + (w - end) / 2, y + h * 0.2 + cap, track=-0.02)
    return f'<path d="{d}" fill="{ink}"/>'


def mark_parts(kind: str, sym: str, x: float, y: float, s: float, ink: str | None = None, sign: str = "#FFFFFF",
               gap: str = "#FFFFFF", colours: tuple[str, str, str] | None = None, uid: str = "m") -> list[str]:
    """[red band, green band, shape, sign], like build_logo.mark_parts, so the Reel end card animates them the same."""
    black, red, green = colours or ((ink,) * 3 if ink else (FLAG_BLACK, FLAG_RED, FLAG_GREEN))
    w = h = s * (0.92 if kind in {"coin", "stamp"} else 0.84)
    rx, ry = x + (s - w) / 2, y + (s - h) / 2
    outline = _shape(kind, rx, ry, w, h)
    clip = f'<clipPath id="c{uid}"><path d="{outline}"/></clipPath>'
    band, white = h * 0.085, h * 0.03
    y1 = ry + h * 0.64
    stripe = lambda yy, col: f'<rect x="{rx:.1f}" y="{yy:.1f}" width="{w:.1f}" height="{band:.1f}" fill="{col}"/>'
    red_el = f'<g clip-path="url(#c{uid})">{stripe(y1 - white, gap)}{stripe(y1, red)}</g>'
    green_el = f'<g clip-path="url(#c{uid})">{stripe(y1 + band, gap)}{stripe(y1 + band + white, green)}</g>'
    body = f'<defs>{clip}</defs><path d="{outline}" fill="{black}"/>'
    return [red_el, green_el, body, _symbol(sym, rx, ry, w, h, sign)]


def mark(kind: str, sym: str, x: float, y: float, s: float, **kw) -> str:
    red, green, body, sign = mark_parts(kind, sym, x, y, s, **kw)
    return body + red + green + sign


ON_DARK = (PAPER, FLAG_RED, FLAG_GREEN)


def lockup(spec: dict, ink: str, stacked: bool, mono: bool = False, sign: str = "#FFFFFF", gap: str = "#FFFFFF",
           uid: str = "m") -> str:
    kind, sym, lines, name = spec["shape"], spec["symbol"], spec["lines"], spec["name"]
    cap, pad = 100, 24
    colours = ON_DARK if (ink == PAPER and not mono) else None
    if colours:
        sign = NIGHT
    common = dict(ink=ink if mono else None, sign=sign, gap=gap, colours=colours, uid=uid)
    if stacked:
        s = 210
        m = mark(kind, sym, pad, pad, s, **common)
        top, ds, ends = pad + s + 46, "", []
        for i, line in enumerate(lines):
            d, e = text_outline(line, cap, pad, top + (i + 1) * cap + i * 30, track=-0.01)
            ds, ends = ds + d, ends + [e]
        w, h = max(ends + [pad + s]) + pad, top + len(lines) * cap + (len(lines) - 1) * 30 + pad
    else:
        s = cap * 1.45
        m = mark(kind, sym, pad, pad - cap * 0.22, s, **common)
        ds, end = text_outline(" ".join(lines), cap, pad + s + 30, pad + cap, track=-0.01)
        w, h = end + pad, cap + 2 * pad + cap * 0.45
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<title>{name}</title>{m}<path d="{ds}" fill="{ink}"/></svg>')


def icon(spec: dict, bg: str, **kw) -> str:
    """Profile picture: the mark alone, centred on a flat field (survives a circle crop)."""
    s = 150
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="512" height="512">'
            f'<title>{spec["name"]} icon</title><rect width="200" height="200" fill="{bg}"/>'
            f'{mark(spec["shape"], spec["symbol"], 25, 25, s, **kw)}</svg>')


def sting_svg(spec: dict) -> str:
    """The animated end card: pieces in groups #red #green #black #q, the name in #word (video.py animates them)."""
    s, x, y = 520, 280, 560
    red, green, black, q = mark_parts(spec["shape"], spec["symbol"], x, y, s, sign=NIGHT, colours=ON_DARK, uid="s")
    cx = x + s / 2
    word = " ".join(spec["lines"])
    d, end = text_outline(word, 60, 0, 0, track=-0.01)
    d, _ = text_outline(word, 60, (1080 - end) / 2, y + s * 0.92 + 150, track=-0.01)
    o = f"transform-origin:{cx:.0f}px {y + s * 0.45:.0f}px"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" width="1080" height="1920">'
            f'<g id="black" style="{o}">{black}</g>'
            f'<g id="red" style="transform-origin:{cx:.0f}px {y + s * 0.6:.0f}px">{red}</g>'
            f'<g id="green" style="transform-origin:{cx:.0f}px {y + s * 0.68:.0f}px">{green}</g>'
            f'<g id="q" style="{o}">{q}</g>'
            f'<g id="word"><path d="{d}" fill="#F8F7F6"/></g></svg>')




# ---------------------------------------------------------------------------
# Street style (Mtaa Mode): the chat bubble
# ---------------------------------------------------------------------------
UNBOUNDED = brands.ROOT / "assets" / "fonts" / "unbounded-latin-wght-normal.woff2"
STREET_KERN = {"TA": -0.07, "AT": -0.07, "AA": -0.01}
_UB: dict = {}


def _unbounded():
    if not _UB:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        # overlaps removed (skia-pathops): Unbounded draws letters like E from overlapping strokes, which leave
        # notches once the outlines become one SVG path. The logo files are committed, so only a rebuild needs it.
        f = instancer.instantiateVariableFont(TTFont(UNBOUNDED), {"wght": 800}, overlap=instancer.OverlapMode.REMOVE)
        _UB.update(glyphs=f.getGlyphSet(), cmap=f.getBestCmap(), hmtx=f["hmtx"], upm=f["head"].unitsPerEm,
                   cap=f["OS/2"].sCapHeight or 0.75 * f["head"].unitsPerEm)
    return _UB


def street_text(text: str, cap_px: float, x: float, baseline: float, track: float = 0.0) -> tuple[str, float]:
    """`text` in Unbounded ExtraBold as path data, capitals `cap_px` tall. Returns (path data, end x)."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    f = _unbounded()
    size = cap_px * f["upm"] / f["cap"]
    scale = size / f["upm"]
    pen = SVGPathPen(f["glyphs"])
    for i, ch in enumerate(text):
        name = f["cmap"][ord(ch)]
        f["glyphs"][name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += f["hmtx"][name][0] * scale + (track + STREET_KERN.get(text[i:i + 2], 0.0)) * size
    return pen.getCommands(), x


def bubble_parts(x: float, y: float, s: float, body: str, dots: str) -> tuple[str, list[str]]:
    """The mark inside the square (x, y, s): a rounded bubble with its tail at the bottom left, and three dots."""
    w, h = s, s * 0.74
    top = y + (s - h - s * 0.16) / 2
    r = s * 0.25
    d = (f"M{x + r:.1f},{top:.1f} H{x + w - r:.1f} Q{x + w:.1f},{top:.1f} {x + w:.1f},{top + r:.1f} V{top + h - r:.1f} "
         f"Q{x + w:.1f},{top + h:.1f} {x + w - r:.1f},{top + h:.1f} H{x + s * 0.42:.1f} L{x + s * 0.12:.1f},{top + h + s * 0.16:.1f} "
         f"L{x + s * 0.2:.1f},{top + h:.1f} H{x + r:.1f} Q{x:.1f},{top + h:.1f} {x:.1f},{top + h - r:.1f} V{top + r:.1f} "
         f"Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} Z")
    cy, dr = top + h / 2, s * 0.078
    dot = [f'<circle cx="{x + w / 2 + k * s * 0.235:.1f}" cy="{cy:.1f}" r="{dr:.1f}" fill="{dots}"/>' for k in (-1, 0, 1)]
    return f'<path d="{d}" fill="{body}"/>', dot


def street_lockup(name: str, lines: list[str], ink: str, body: str, dots: str, stacked: bool) -> str:
    cap, pad = 100, 24
    if stacked:
        s = 220
        b, dd = bubble_parts(pad, pad, s, body, dots)
        top, ds, ends = pad + s + 40, "", []
        for i, line in enumerate(lines):
            d, e = street_text(line, cap, pad, top + (i + 1) * cap + i * 34, track=0.0)
            ds, ends = ds + d, ends + [e]
        w, h = max(ends + [pad + s]) + pad, top + len(lines) * cap + (len(lines) - 1) * 34 + pad
    else:
        s = cap * 1.5
        b, dd = bubble_parts(pad, pad - cap * 0.2, s, body, dots)
        ds, end = street_text(" ".join(lines), cap, pad + s + 34, pad + cap)
        w, h = end + pad, cap + 2 * pad + cap * 0.3
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}">'
            f'<title>{name}</title>{b}{"".join(dd)}<path d="{ds}" fill="{ink}"/></svg>')


def street_icon(name: str, bg: str, body: str, dots: str) -> str:
    b, dd = bubble_parts(36, 40, 128, body, dots)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="512" height="512">'
            f'<title>{name} icon</title><rect width="200" height="200" fill="{bg}"/>{b}{"".join(dd)}</svg>')


def street_sting(name: str, lines: list[str], body: str, dots: str, word: str) -> str:
    """End card groups for video.py: #black the bubble, #red #green #q the three dots (typing), #word the name."""
    s, x, y = 500, 290, 560
    b, (d1, d2, d3) = bubble_parts(x, y, s, body, dots)
    cx = x + s / 2
    text = " ".join(lines)
    d, end = street_text(text, 64, 0, 0)
    d, _ = street_text(text, 64, (1080 - end) / 2, y + s + 170)
    o = f"transform-origin:{cx:.0f}px {y + s * 0.45:.0f}px"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" width="1080" height="1920">'
            f'<g id="black" style="{o}">{b}</g>'
            f'<g id="red" style="{o}">{d1}</g><g id="green" style="{o}">{d2}</g><g id="q" style="{o}">{d3}</g>'
            f'<g id="word"><path d="{d}" fill="{word}"/></g></svg>')


def build_street(b: dict, out) -> dict[str, str]:
    P = b["palette"]
    lime, night, paper, ink = P["lime"]["300"], P["ink"]["950"], P["ink"]["50"], P["ink"]["900"]
    name, lines = b["name"], b["logo"]["lines"]
    files = {
        "wordmark-on-light.svg": street_lockup(name, lines, ink, ink, lime, False),
        "wordmark-on-dark.svg": street_lockup(name, lines, paper, lime, night, False),
        "stacked-on-light.svg": street_lockup(name, lines, ink, ink, lime, True),
        "stacked-on-dark.svg": street_lockup(name, lines, paper, lime, night, True),
        "wordmark-mono-light.svg": street_lockup(name, lines, "#FFFFFF", "#FFFFFF", night, False),
        "wordmark-mono-dark.svg": street_lockup(name, lines, night, night, "#FFFFFF", False),
        "stacked-mono-light.svg": street_lockup(name, lines, "#FFFFFF", "#FFFFFF", night, True),
        "stacked-mono-dark.svg": street_lockup(name, lines, night, night, "#FFFFFF", True),
        "icon-night.svg": street_icon(name, night, lime, night),
        "icon-paper.svg": street_icon(name, paper, ink, lime),
        "icon-red.svg": street_icon(name, lime, night, lime),
        "sting.svg": street_sting(name, lines, lime, night, paper),
    }
    return files


def build(slug: str | None = None) -> list[str]:
    b = brands.brand(slug)
    spec = {**b["logo"], "name": b["name"]}
    out = (brands.HOME if slug is None else brands.HERE / "brands" / brands.slug_of(slug)) / "logo"
    out.mkdir(parents=True, exist_ok=True)
    if spec.get("style") == "street":
        files = build_street(b, out)
        for name, svg in files.items():
            (out / name).write_text(svg, encoding="utf-8")
        return sorted(files)
    files = {}
    for name, ink in {"on-light": P["ink"]["900"], "on-dark": PAPER}.items():
        files[f"wordmark-{name}.svg"] = lockup(spec, ink, stacked=False)
        files[f"stacked-{name}.svg"] = lockup(spec, ink, stacked=True)
    for name, ink, sign, bg in (("mono-light", "#FFFFFF", SUN, SUN), ("mono-dark", NIGHT, "#FFFFFF", "#FFFFFF")):
        files[f"wordmark-{name}.svg"] = lockup(spec, ink, stacked=False, mono=True, sign=sign, gap=bg)
        files[f"stacked-{name}.svg"] = lockup(spec, ink, stacked=True, mono=True, sign=sign, gap=bg)
    files["icon-paper.svg"] = icon(spec, "#FFFFFF")
    files["icon-red.svg"] = files["icon-paper.svg"]
    files["icon-night.svg"] = icon(spec, NIGHT, gap=PAPER, colours=ON_DARK, sign=NIGHT)
    files["sting.svg"] = sting_svg(spec)
    for name, svg in files.items():
        (out / name).write_text(svg, encoding="utf-8")
    return sorted(files)


if __name__ == "__main__":
    print(build())
