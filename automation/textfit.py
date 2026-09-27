"""
textfit.py — measures text with the brand's real font files, so layouts are computed, not guessed.

The browser wraps text greedily at spaces; we do the same with the font's own advance widths
(variable font instanced at the weight the CSS uses). A small safety margin covers kerning and
sub-pixel rounding, so our estimate is never shorter than what Chromium draws.

    >>> lines("Sasa naandika mwenyewe, AI inasaidia tu na muundo.", px=27, weight=700, width=304)
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FILES = {"Figtree": "figtree-latin-wght-normal.woff2", "Unbounded": "unbounded-latin-wght-normal.woff2"}
SAFETY = 1.015  # measured width x margin: errs towards one more line, never one fewer


@lru_cache(maxsize=None)
def _advances(family: str, weight: int) -> tuple[dict, int]:
    """Character -> advance width (font units) at this weight, plus units-per-em."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    font = TTFont(FONTS / FILES[family])
    if "fvar" in font:
        axis = next(a for a in font["fvar"].axes if a.axisTag == "wght")
        font = instantiateVariableFont(font, {"wght": max(axis.minValue, min(axis.maxValue, weight))})
    cmap, hmtx = font.getBestCmap(), font["hmtx"].metrics
    widths = {chr(cp): hmtx[name][0] for cp, name in cmap.items() if name in hmtx}
    return widths, font["head"].unitsPerEm


def width(text: str, px: float, family: str = "Figtree", weight: int = 700, tracking: float = 0.0) -> float:
    """Rendered width in px. `tracking` is CSS letter-spacing in em (e.g. -0.03)."""
    widths, upm = _advances(family, weight)
    fallback = widths.get("n", upm // 2)  # unknown glyphs (emoji etc.) counted as a wide-ish letter
    return (sum(widths.get(ch, fallback) for ch in text) * px / upm + tracking * px * len(text)) * SAFETY


def wrap(text: str, px: float, width_px: float, family: str = "Figtree", weight: int = 700,
         tracking: float = 0.0) -> list[str]:
    """Greedy wrap like the browser. Hyphenated words stay whole (render.nobreak keeps them unbroken)."""
    words = re.split(r"\s+", text.strip())
    out, line = [], ""
    for w in words:
        trial = f"{line} {w}" if line else w
        if not line or width(trial, px, family, weight, tracking) <= width_px:
            line = trial
        else:
            out.append(line)
            line = w
    if line:
        out.append(line)
    return out or [""]


def lines(text: str, px: float, weight: int, width: float, family: str = "Figtree") -> int:
    return len(wrap(text, px, width, family, weight))


def fit_display(text: str, box_w: float, max_lines: int, base: float) -> int:
    """Largest size <= base at which a display headline (Unbounded 800, -0.03em) fits the box:
    at most max_lines lines, and no single word wider than the box (a long word can't wrap)."""
    text = str(text)
    for px in range(int(base), 11, -1):
        rows = wrap(text, px, box_w, "Unbounded", 800, -0.03)
        if len(rows) <= max_lines and all(width(r, px, "Unbounded", 800, -0.03) <= box_w for r in rows):
            return px
    return 12


# Comic bubble geometry: must mirror .bub in templates/vichekesho.html.j2 (border-box)
BUBBLE = {"w": 360, "pad_x": 24, "pad_y": 18, "border": 4, "line_h": 1.22,
          "say": {"px": 27, "weight": 700}, "sms": {"px": 25, "weight": 600}, "sms_label": 17 * 1.22 + 4}


def bubble_height(text: str, sms: bool) -> float:
    kind = BUBBLE["sms" if sms else "say"]
    inner = BUBBLE["w"] - 2 * BUBBLE["pad_x"] - 2 * BUBBLE["border"]
    n = lines(text, kind["px"], kind["weight"], inner)
    label = BUBBLE["sms_label"] if sms else 0
    return 2 * BUBBLE["border"] + 2 * BUBBLE["pad_y"] + label + n * kind["px"] * BUBBLE["line_h"]
