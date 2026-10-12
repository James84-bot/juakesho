"""
palette.py — the Jua Kesho colour system: four families, eleven shades each, built in OKLCH
so every step looks evenly spaced to the eye (not just in hex).

    python palette.py          # prints the ramps and writes them into brand.json ("palette")

Families (the colours of the Kenyan flag: they belong to every Kenyan and to no party)
  ink    black to paper white. Backgrounds, text, rules: 90% of every design.
  shuka  flag red. The signature: the sun in the logo, series tags, labels, the one highlight per design,
         and warnings (FALSE, SCAM, BROKEN promise).
  chai   flag green. TRUE, KEPT, good news, Africa's wins, the horizon in the logo.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]

# anchor: (step, OKLCH L, C, hue). The anchor is the brand swatch; the ramp is interpolated around it.
FAMILIES = {
    "ink":   {"anchor": (950, 0.155, 0.004, 60), "c_max": 0.005, "hue_dark": 60, "hue_light": 75,
              # neutrals need finer steps at the light end (paper, dividers) than a straight line gives
              "L": [0.977, 0.952, 0.905, 0.835, 0.730, 0.620, 0.510, 0.405, 0.305, 0.215, 0.155]},
    "shuka": {"anchor": (600, 0.520, 0.205, 27),  "c_max": 0.215, "hue_dark": 24,  "hue_light": 22},
    "chai":  {"anchor": (700, 0.470, 0.140, 150), "c_max": 0.150, "hue_dark": 152, "hue_light": 145},
}
L_TOP, L_BOTTOM = 0.977, 0.165


def oklch_to_srgb(L: float, C: float, h: float) -> tuple[float, float, float]:
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lin = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    return tuple(12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055 for v in lin)


def in_gamut(rgb) -> bool:
    return all(-1e-4 <= v <= 1 + 1e-4 for v in rgb)


def to_hex(L: float, C: float, h: float) -> str:
    while C > 0 and not in_gamut(oklch_to_srgb(L, C, h)):   # keep hue and lightness, give up chroma
        C -= 0.002
    r, g, b = (round(min(1, max(0, v)) * 255) for v in oklch_to_srgb(L, max(C, 0), h))
    return f"#{r:02X}{g:02X}{b:02X}"


def ramp(spec: dict) -> dict[str, str]:
    step_a, L_a, C_a, h_a = spec["anchor"]
    i_a = STEPS.index(step_a)
    out = {}
    for i, step in enumerate(STEPS):
        if i <= i_a:   # paper side of the anchor
            t = i / i_a if i_a else 1
            L = L_TOP + (L_a - L_TOP) * t
            h = spec["hue_light"] + (h_a - spec["hue_light"]) * t
        else:          # night side
            t = (i - i_a) / (len(STEPS) - 1 - i_a)
            L = L_a + (L_BOTTOM - L_a) * t
            h = h_a + (spec["hue_dark"] - h_a) * t
        if "L" in spec:
            L = spec["L"][i]
        # chroma peaks at the anchor and eases off towards both ends (pastel tints, deep darks)
        dist = abs(i - i_a) / max(i_a, len(STEPS) - 1 - i_a)
        C = C_a if i == i_a else spec["c_max"] * (1 - 0.75 * dist ** 1.6)
        out[str(step)] = to_hex(L, C, h)
    return out


def luminance(hex_: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def build() -> dict:
    return {name: ramp(spec) for name, spec in FAMILIES.items()}


if __name__ == "__main__":
    pal = build()
    for name, r in pal.items():
        print(f"{name:6}", " ".join(f"{k}:{v}" for k, v in r.items()))
    path = Path(__file__).resolve().parent / "brand.json"
    brand = json.loads(path.read_text(encoding="utf-8"))
    brand["palette"] = pal
    path.write_text(json.dumps(brand, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
