"""
brand_logo.py — the logo set of a brand other than Kenya on Record, in the same family: a dark shape crossed by the
Kenyan flag's red and green bands (with their white edges) and a white symbol, then the name in Inter Tight Black.
Each brand has its own shape, so the five read as one network and still apart at a glance:

    scoreboard  Full Time Kenya      a rounded scoreboard, "FT" on it
    coin        Shilling Brief       a coin, "Sh" on it
    shield      Verified Jobs Kenya  a badge, a tick on it
    stamp       Kenya Postcards      a postage stamp, Mount Kenya's peak on it

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
    if sym == "peak":   # Mount Kenya: a twin summit with snow, as a single shape
        b, t = y + h * 0.56, y + h * 0.17
        d = (f"M{x + w * 0.2:.1f},{b:.1f} L{x + w * 0.44:.1f},{t + h * 0.06:.1f} L{x + w * 0.5:.1f},{t + h * 0.12:.1f} "
             f"L{x + w * 0.56:.1f},{t:.1f} L{x + w * 0.8:.1f},{b:.1f} Z")
        return f'<path d="{d}" fill="{ink}"/>'
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


def build(slug: str | None = None) -> list[str]:
    b = brands.brand(slug)
    spec = {**b["logo"], "name": b["name"]}
    out = (brands.HOME if slug is None else brands.HERE / "brands" / brands.slug_of(slug)) / "logo"
    out.mkdir(parents=True, exist_ok=True)
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
