"""
stickers.py — the Jua Kesho WhatsApp sticker pack.

WhatsApp spec: 512x512 WebP with transparent background, each under 100 KB,
3-30 stickers per pack, plus a 96x96 PNG tray icon under 50 KB.
Output: exports/stickers/  (import with a sticker-maker app, or ship in an app later)

    python stickers.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

import brandkit as bk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "exports" / "stickers"
FONTS = (ROOT / "assets" / "fonts").as_uri()
C = bk.C

# (file, art, label, label colour)
STICKERS = [
    ("sawa", ("jua", "happy"), "Sawa sawa!", C["chai"]),
    ("eh", ("jua", "wow"), "Eh?!", C["shuka"]),
    ("manze", ("jua", "thinking"), "Manze…", C["jacaranda"]),
    ("usiibiwe", ("jua", "wow"), "Usiibiwe!", C["shuka"]),
    ("no-cap", ("jua", "cool"), "No cap", C["chai"]),
    ("cap", ("jua", "laugh"), "CAP!", C["shuka"]),
    ("kesho", ("jua", "visor"), "Kesho iko hapa", C["jacaranda"]),
    ("save-this", ("jua", "wink"), "Save this!", C["ziwa"]),
    ("on-it", ("techie", "point"), "On it!", C["jacaranda"]),
    ("cheer", ("student", "cheer"), "Tumefika!", C["chai"]),
    ("shosh", ("shosh", "wave"), "Shosh says hi", C["shuka"]),
    ("scam", ("mama_mboga", "shrug"), "Hii ni scam!", C["shuka"]),
]


def art_svg(kind: str, pose_or_expr: str) -> str:
    if kind == "jua":
        return f'<svg viewBox="0 0 200 200" class="art">{bk.mascot(pose_or_expr)}</svg>'
    mood = {"cheer": "happy", "point": "happy", "wave": "happy", "shrug": "worried"}.get(pose_or_expr, "happy")
    return (f'<svg viewBox="0 0 200 260" class="art art--person">'
            f'{bk.stick(kind, 100, 245, pose_or_expr, mood, 1.0)}</svg>')


def page(art: str, label: str, color: str) -> str:
    # Die-cut look: a thick white outline traced around everything via an SVG morphology filter
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
{bk.font_faces(FONTS)}
html,body{{margin:0;background:transparent}}
#s{{width:512px;height:512px;position:relative;filter:url(#cut)}}
.art{{position:absolute;left:66px;top:30px;width:380px;height:380px}}
.art--person{{left:96px;top:20px;width:320px;height:416px}}
.label{{position:absolute;left:0;right:0;bottom:34px;text-align:center}}
.label span{{display:inline-block;padding:10px 26px 14px;border-radius:22px;background:{color};color:#fff;
  font:800 {44 if len(label) < 11 else 34}px/1 "Unbounded";letter-spacing:-.02em;transform:rotate(-4deg);
  box-shadow:5px 6px 0 {C["usiku"]}}}
</style></head><body>
<svg width="0" height="0" style="position:absolute"><filter id="cut" x="-10%" y="-10%" width="120%" height="120%">
<feMorphology in="SourceAlpha" operator="dilate" radius="9" result="d"/>
<feFlood flood-color="#ffffff"/><feComposite in2="d" operator="in" result="w"/>
<feDropShadow in="w" dx="0" dy="3" stdDeviation="3" flood-color="#1D1433" flood-opacity=".25" result="ws"/>
<feMerge><feMergeNode in="ws"/><feMergeNode in="SourceGraphic"/></feMerge></filter></svg>
<div id="s">{art}<div class="label"><span>{label}</span></div></div></body></html>"""


def webp_under(img: Image.Image, target: Path, limit: int = 100_000) -> int:
    for q in (90, 80, 70, 60, 50, 40):
        img.save(target, "WEBP", quality=q, method=6)
        size = target.stat().st_size
        if size < limit:
            return size
    raise RuntimeError(f"{target.name} stays over {limit} bytes")


def main() -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 600, "height": 600})
        for name, (kind, var), label, color in STICKERS:
            tmp = OUT / f".{name}.html"
            tmp.write_text(page(art_svg(kind, var), label, color), encoding="utf-8")
            pg.goto(tmp.as_uri())
            pg.evaluate("document.fonts.ready")
            png = OUT / f".{name}.png"
            pg.locator("#s").screenshot(path=str(png), omit_background=True)
            img = Image.open(png).convert("RGBA").resize((512, 512), Image.LANCZOS)
            size = webp_under(img, OUT / f"{name}.webp")
            tmp.unlink()
            png.unlink()
            print(f"  ✓ {name}.webp  {size // 1024} KB")
        browser.close()
    tray = Image.open(OUT / "sawa.webp").convert("RGBA").resize((96, 96), Image.LANCZOS)
    tray.save(OUT / "tray.png", optimize=True)
    print(f"  ✓ tray.png  {(OUT / 'tray.png').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
