"""
mtaa_art.py — the places Mtaa Mode's scenes happen in, drawn as flat vector backdrops (1080x1920, the floor at
y=1500, where the cast's feet stand). Everyday Kenyan settings, original drawings: no brand, no real business, no
real person. Signs carry no prices.

    plot      a rental block's courtyard: steel doors, a washing line, a jerrycan, the water tank on the roof
    matatu    inside a matatu: the neon strip, the seats, the city sliding past the windows (id "drift" moves)
    kibanda   a roadside kiosk: mabati roof, mandazi and chapati on the counter, flasks, a bench
    nyumbani  Mathe's sitting room: the sofa with its crochet doilies, the wall clock, family photos, the TV

Each place says where the cast stand (SPOTS by cast size) and whether they sit (matatu).
"""
from __future__ import annotations

import random

W, H, FLOOR = 1080, 1920, 1500
PLACES = ("plot", "matatu", "kibanda", "nyumbani")
SEATED = {"matatu"}
SPOTS = {2: [300, 780], 3: [210, 540, 870]}


def _r(x, y, w, h, fill, rx=0, extra=""):
    return f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{rx}" fill="{fill}" {extra}/>'


def _sky(top_color="#8FD3F4", bottom="#D9F1FB", h=700, seed=0):
    rnd = random.Random(seed)
    out = (f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top_color}"/>'
           f'<stop offset="1" stop-color="{bottom}"/></linearGradient></defs>' + _r(0, 0, W, h, "url(#sky)"))
    for _ in range(3):
        cx, cy, s = rnd.randint(80, 1000), rnd.randint(90, 330), rnd.uniform(0.7, 1.2)
        out += "".join(f'<ellipse cx="{cx + dx * s:.0f}" cy="{cy + dy * s:.0f}" rx="{rx * s:.0f}" ry="{ry * s:.0f}" fill="#FFFFFF" opacity=".9"/>'
                       for dx, dy, rx, ry in ((0, 0, 70, 34), (-56, 12, 50, 26), (58, 10, 56, 28)))
    return out


def plot() -> str:
    """A Nairobi rental block's courtyard."""
    o = _sky(seed=3, h=520)
    # the block: cream walls, the maroon band painted along the bottom, the upper floor's windows with grills
    o += _r(0, 300, W, FLOOR - 300, "#EADFC8")
    o += _r(0, 300, W, 26, "#D6C7A8")
    o += _r(0, 1262, W, FLOOR - 1262, "#7A2E2E") + _r(0, 1256, W, 10, "#5E2020")
    for x in (70, 420, 770):
        o += _r(x, 380, 240, 190, "#3D5A73", 6) + _r(x + 10, 390, 220, 170, "#9CC3DB", 4)
        o += "".join(_r(x + 10 + i * 31, 390, 6, 170, "#2B2B2B") for i in range(8)) + _r(x + 10, 470, 220, 6, "#2B2B2B")
        o += _r(x - 10, 570, 260, 14, "#D6C7A8")
    # the roof tank on its stand
    o += _r(860, 150, 16, 170, "#5A5A5A") + _r(1004, 150, 16, 170, "#5A5A5A")
    o += '<path d="M840,150 Q840,60 940,58 Q1040,60 1040,150 Z" fill="#1E1E22"/>' + _r(840, 140, 200, 30, "#1E1E22", 8)
    o += "".join(f'<path d="M852,{y} H1028" stroke="#2E2E33" stroke-width="5"/>' for y in (96, 120))
    # steel doors with stencilled numbers
    for x, n, col in ((40, "12", "#2F5D50"), (420, "13", "#2F4E7A"), (800, "14", "#2F5D50")):
        o += _r(x - 14, 820, 268, FLOOR - 820, "#C9BB9C")
        o += _r(x, 834, 240, FLOOR - 834, col, 4)
        o += "".join(_r(x + 16, 860 + i * 150, 208, 120, "rgba(0,0,0,.12)", 4) for i in range(4))
        o += f'<circle cx="{x + 206}" cy="1180" r="11" fill="#C8B26A"/>'
        o += (f'<text x="{x + 120}" y="940" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="56" '
              f'fill="#F2EFE6" opacity=".9">{n}</text>')
    # the washing line across the courtyard
    o += '<path d="M0,660 Q540,740 1080,660" fill="none" stroke="#3B3B3B" stroke-width="4"/>'
    for x, col, kind in ((120, "#E8452C", "tee"), (300, "#F7F7F9", "tee"), (520, "#3A7BD5", "towel"), (720, "#F9B64F", "tee"),
                         (900, "#7B4FD0", "towel")):
        y = 660 + 80 * (1 - ((x - 540) / 540) ** 2) - 4
        if kind == "tee":
            o += (f'<path d="M{x - 50},{y} L{x - 18},{y} Q{x},{y + 14} {x + 18},{y} L{x + 50},{y} L{x + 64},{y + 40} L{x + 40},{y + 50} '
                  f'L{x + 40},{y + 140} L{x - 40},{y + 140} L{x - 40},{y + 50} L{x - 64},{y + 40} Z" fill="{col}"/>')
        else:
            o += _r(x - 46, y, 92, 150, col, 4) + _r(x - 46, y + 120, 92, 12, "rgba(255,255,255,.4)")
        o += _r(x - 30, y - 8, 10, 22, "#C8B26A", 2) + _r(x + 20, y - 8, 10, 22, "#C8B26A", 2)
    # the floor: concrete, a yellow jerrycan by door 13
    o += _r(0, FLOOR, W, H - FLOOR, "#A39D92")
    o += "".join(f'<path d="M{x},{FLOOR + 40 + (x % 7) * 30} l{60 + x % 40},{18}" stroke="rgba(0,0,0,.12)" stroke-width="4"/>'
                 for x in range(40, 1080, 170))
    o += ('<g transform="translate(660 1390)"><rect x="0" y="0" width="92" height="110" rx="12" fill="#F2C12E"/>'
          '<rect x="54" y="-22" width="22" height="26" rx="4" fill="#E0A800"/><rect x="10" y="-12" width="40" height="16" rx="8" fill="#E0A800"/>'
          '<rect x="0" y="40" width="92" height="8" fill="rgba(0,0,0,.12)"/></g>')
    return o


def matatu() -> str:
    """Inside a matatu: purple interior, a neon strip, the city sliding past (the group "drift" is moved by time)."""
    o = _r(0, 0, W, H, "#241A33")
    o += _r(0, 0, W, 300, "#1A1226")
    o += _r(0, 296, W, 12, "#C3F62A", 0, 'opacity=".9"') + _r(0, 296, W, 36, "#C3F62A", 0, 'opacity=".12"')
    o += '<path d="M0,250 H1080" stroke="#8C8C99" stroke-width="10"/>'   # the grab rail
    o += "".join(f'<path d="M{x},250 V300" stroke="#8C8C99" stroke-width="6"/>' for x in (160, 540, 920))
    # windows: the outside, sliding
    o += '<defs><clipPath id="win">' + "".join(_r(x, 400, 300, 380, "#000", 26) for x in (40, 390, 740)) + '</clipPath></defs>'
    o += '<g clip-path="url(#win)">' + _r(0, 380, W, 420, "#9AD8F2")
    rnd = random.Random(7)
    city = ""
    x = -40
    while x < 3600:
        w, h = rnd.randint(90, 200), rnd.randint(140, 330)
        col = rnd.choice(["#5E6B7A", "#6F7D8C", "#4E5966", "#7C6A5A"])
        city += _r(x, 800 - h, w, h, col)
        city += "".join(_r(x + 14 + i * 34, 820 - h + j * 46, 18, 26, "#F2E7B5", 0, 'opacity=".55"')
                        for i in range(max(1, (w - 20) // 34)) for j in range(max(1, (h - 40) // 46)))
        x += w + rnd.randint(10, 40)
    o += f'<g id="drift">{city}</g>' + _r(0, 700, W, 100, "#3E3A36") + '</g>'
    o += "".join(_r(x, 400, 300, 380, "none", 26, 'stroke="#14101C" stroke-width="16"') for x in (40, 390, 740))
    o += ('<g transform="translate(540 880)"><rect x="-210" y="-30" width="420" height="60" rx="30" fill="#FC4AA1"/>'
          '<text x="0" y="12" text-anchor="middle" font-family="Inter Tight" font-weight="800" font-size="30" fill="#0E0E12">'
          'USIONGEE NA DEREVA</text></g>')
    # the seat backs (the cast sit in front of them) and the floor
    o += _r(30, 1060, 1020, 330, "#5B1F2E", 40) + _r(30, 1060, 1020, 40, "#6E2738", 40)
    o += "".join(f'<path d="M{x},1110 V1370" stroke="rgba(0,0,0,.18)" stroke-width="6"/>' for x in (290, 540, 790))
    o += _r(0, 1360, W, 50, "#4A1825", 10)
    o += _r(0, FLOOR, W, H - FLOOR, "#1A1420") + "".join(_r(0, FLOOR + 30 + i * 70, W, 8, "#2A2230") for i in range(6))
    return o


def kibanda() -> str:
    """A roadside kiosk, morning."""
    o = _sky("#F7C59F", "#FBE7D2", h=900, seed=11)
    rnd = random.Random(4)
    for x in range(-20, 1080, 140):   # the town behind
        h = rnd.randint(200, 420)
        o += _r(x, 900 - h, 130, h, rnd.choice(["#C9B8A6", "#B9A795", "#D4C3AF"]))
    o += _r(0, 900, W, FLOOR - 900, "#C98F5E")
    # the kiosk: posts, mabati roof, the counter window
    o += _r(110, 560, 26, 900, "#6B4423") + _r(944, 560, 26, 900, "#6B4423")
    roof = "M60,600 " + " ".join(f"L{60 + i * 30},{575 if i % 2 else 600}" for i in range(33)) + " L1020,640 L60,640 Z"
    o += f'<path d="{roof}" fill="#A9B4BC"/>' + _r(60, 630, 960, 18, "#7F8A93")
    o += _r(136, 660, 808, 420, "#4FA3C7")
    o += _r(176, 700, 728, 300, "#3A3A40", 8)
    o += ('<g transform="translate(540 760)"><rect x="-330" y="-40" width="660" height="80" rx="10" fill="#F2EFE6"/>'
          '<text x="0" y="13" text-anchor="middle" font-family="Unbounded" font-weight="800" font-size="34" fill="#7A2E2E" '
          'textLength="600" lengthAdjust="spacingAndGlyphs">CHAI · MANDAZI · CHAPO</text></g>')
    # the counter and what is on it
    o += _r(136, 1000, 808, 60, "#8A5A2B") + _r(136, 1060, 808, 400, "#4FA3C7") + _r(136, 1060, 808, 16, "#3C88AA")
    for i in range(7):   # mandazi on a tray
        x = 230 + (i % 4) * 46 + (i // 4) * 23
        y = 984 - (i // 4) * 26
        o += f'<path d="M{x - 26},{y + 14} L{x},{y - 18} L{x + 26},{y + 14} Z" fill="#D9963F" stroke="#B9772A" stroke-width="3"/>'
    o += _r(200, 996, 260, 10, "#B0B0B0", 4)
    for i in range(5):   # chapati stack
        o += f'<ellipse cx="620" cy="{994 - i * 10}" rx="86" ry="18" fill="#E2B56A" stroke="#C99A4F" stroke-width="3"/>'
    for x, col in ((780, "#D93A2F"), (850, "#2F6FD9")):   # flasks
        o += _r(x - 26, 880, 52, 120, col, 14) + _r(x - 18, 862, 36, 24, "#E8E8E8", 6)
    # the bench and the ground
    o += _r(230, 1330, 620, 34, "#7A4A22", 6) + _r(270, 1364, 22, 136, "#5A3518") + _r(788, 1364, 22, 136, "#5A3518")
    o += _r(0, FLOOR, W, H - FLOOR, "#B97A4A")
    o += "".join(f'<ellipse cx="{x}" cy="{FLOOR + 60 + (x * 7) % 260}" rx="{10 + x % 9}" ry="6" fill="#9C6338"/>' for x in range(30, 1080, 77))
    return o


def nyumbani() -> str:
    """Mathe's sitting room."""
    o = _r(0, 0, W, FLOOR, "#E9D9B5") + _r(0, 1180, W, 12, "#C9B48C")
    # wall clock, photos, the calendar
    o += ('<g transform="translate(540 420)"><circle r="92" fill="#F7F3EA" stroke="#6B4423" stroke-width="14"/>'
          + "".join(f'<rect x="-3" y="-80" width="6" height="16" fill="#3A2A1E" transform="rotate({a})"/>' for a in range(0, 360, 30))
          + '<path d="M0,0 L0,-56" stroke="#2A1E16" stroke-width="8" stroke-linecap="round"/>'
          '<path d="M0,0 L40,18" stroke="#2A1E16" stroke-width="6" stroke-linecap="round"/><circle r="8" fill="#2A1E16"/></g>')
    for x, y, w, h in ((140, 330, 150, 190), (790, 300, 170, 130), (820, 460, 120, 150)):
        o += _r(x, y, w, h, "#8A5A2B", 6) + _r(x + 12, y + 12, w - 24, h - 24, "#C7D9C9")
        o += f'<circle cx="{x + w / 2:.0f}" cy="{y + h * 0.42:.0f}" r="{min(w, h) * 0.17:.0f}" fill="#6B4226"/>'
        o += f'<path d="M{x + w * 0.25:.0f},{y + h - 12} Q{x + w / 2:.0f},{y + h * 0.5:.0f} {x + w * 0.75:.0f},{y + h - 12}Z" fill="#7B4FD0"/>'
    o += _r(330, 600, 130, 170, "#F7F7F9", 4) + _r(330, 600, 130, 40, "#D93A2F", 4)
    o += "".join(_r(344 + (i % 5) * 22, 656 + (i // 5) * 22, 14, 14, "#C9C8CD") for i in range(20))
    # the sofa with the doilies, the TV on its stand
    o += _r(40, 940, 640, 300, "#7A2E2E", 40) + _r(40, 1140, 640, 120, "#6A2424", 30)
    o += _r(20, 1020, 70, 240, "#6A2424", 30) + _r(630, 1020, 70, 240, "#6A2424", 30)
    for x in (130, 300, 470):
        o += (f'<g transform="translate({x} 950)"><path d="M0,0 H120 V70 Q60,104 0,70 Z" fill="#F7F7F9"/>'
              + "".join(f'<circle cx="{10 + i * 20}" cy="{30 + (i % 2) * 18}" r="6" fill="none" stroke="#DADADA" stroke-width="3"/>' for i in range(6))
              + '</g>')
    o += _r(760, 900, 260, 300, "#8A5A2B", 8) + _r(780, 760, 220, 150, "#141418", 10) + _r(792, 772, 196, 126, "#2E3A4A", 6)
    o += '<path d="M770,900 H1010 V930 Q890,960 770,930 Z" fill="#F7F7F9"/>'
    # the carpet and the floor
    o += _r(0, FLOOR, W, H - FLOOR, "#9C6B3F")
    o += _r(120, FLOOR + 40, 840, 300, "#B23A48", 20) + _r(150, FLOOR + 70, 780, 240, "none", 14, 'stroke="#F2C12E" stroke-width="10"')
    return o


DRAW = {"plot": plot, "matatu": matatu, "kibanda": kibanda, "nyumbani": nyumbani}


def backdrop(place: str) -> str:
    return DRAW[place]()
