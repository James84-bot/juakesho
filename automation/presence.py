"""
presence.py — the profile kit: Story highlight covers and the three pinned-post briefs, in the brand.

The profile is the shop window: someone lands from a Reel, looks at the grid, the highlights and the bio for
about three seconds, and decides to follow or leave. These covers make the highlights read as one system:
ink background, one white line icon or numeral, one red marker. Instagram shows highlights as a circle cut
from the centre of a 1080x1920 frame, so everything sits well inside the centre 1080px circle.

    python presence.py        # writes exports/presence/highlight-*.png and a contact sheet
"""
from __future__ import annotations

import json
from pathlib import Path

import brandkit as bk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "exports" / "presence"
FONTS = (ROOT / "assets" / "fonts").as_uri()
P = bk.P
INK, RED, WHITE = P["ink"]["950"], P["shuka"]["600"], "#FFFFFF"
STROKE = f'fill="none" stroke="{WHITE}" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"'

# Each icon is drawn in a 400x400 box. One red element per cover, never more.
ICONS = {
    # Ahadi (promise tracker): a checklist, one item still open
    "ahadi": f"""<path d="M70 92 l34 34 l58 -70" {STROKE}/><path d="M214 96 H340" {STROKE}/>
        <path d="M70 206 l34 34 l58 -70" {STROKE}/><path d="M214 210 H340" {STROKE}/>
        <rect x="72" y="282" width="84" height="84" rx="10" fill="none" stroke="{RED}" stroke-width="22"/>
        <path d="M214 324 H340" {STROKE}/>""",
    # Receipts: a torn-edge slip
    "receipts": f"""<path d="M96 40 H304 V352 l-26 -18 l-26 18 l-26 -18 l-26 18 l-26 -18 l-26 18 l-26 -18 l-26 18 Z" {STROKE}/>
        <path d="M142 116 H258 M142 176 H258" {STROKE}/><rect x="138" y="226" width="124" height="40" fill="{RED}"/>""",
    # Hatutasahau (we won't forget): a candle
    "hatutasahau": f"""<rect x="150" y="170" width="100" height="190" rx="10" {STROKE}/>
        <path d="M200 170 V136" {STROKE}/>
        <path d="M200 40 C232 80 238 104 222 124 C212 136 188 136 178 124 C162 104 168 80 200 40 Z" fill="{RED}"/>""",
    # Civic 101: the numeral is the icon
    "civic": f"""<text x="200" y="262" text-anchor="middle" font-family="Inter Tight" font-weight="900" font-size="196"
        letter-spacing="-8" fill="{WHITE}">1<tspan fill="{RED}">0</tspan>1</text>""",
    # Polls: three bars, the winner in red
    "polls": f"""<path d="M60 350 H340" {STROKE}/><rect x="84" y="210" width="62" height="110" rx="6" fill="{WHITE}"/>
        <rect x="170" y="80" width="62" height="240" rx="6" fill="{RED}"/><rect x="256" y="160" width="62" height="160" rx="6" fill="{WHITE}"/>""",
    # Sisi (who we are, how we check facts): a magnifier over a line of text
    "sisi": f"""<circle cx="174" cy="170" r="104" {STROKE}/><path d="M250 246 L338 334" fill="none" stroke="{RED}" stroke-width="34" stroke-linecap="round"/>
        <path d="M122 150 H226 M122 196 H194" {STROKE}/>""",
}

# Highlight name (shown under the circle, max ~15 chars) -> icon, and what goes inside it
HIGHLIGHTS = [
    ("PROMISES", "ahadi", "The promise tracker: every 'kept / broken / stalled' post, newest first."),
    ("SOURCES", "receipts", "Screenshots of the sources behind our biggest posts: Auditor-General, Hansard, gazette notices."),
    ("HATUTASAHAU", "hatutasahau", "One Story per date we remember, re-shared on its anniversary."),
    ("YOUR RIGHTS", "civic", "Your rights in 15 seconds: arrest, protest, voter registration, public participation."),
    ("POLLS", "polls", "Every Story poll and its result. People come back to see how they voted against everyone else."),
    ("ABOUT", "sisi", "Who we are (ordinary Kenyans, every tribe and county), our rules (sources, no tribe, no campaigning), how to send a tip."),
]


def cover_html(icon: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{bk.font_faces(FONTS)}
html,body{{margin:0;width:1080px;height:1920px;background:{INK};}}
.c{{position:absolute;left:0;top:420px;width:1080px;height:1080px;display:grid;place-items:center;}}
svg{{width:640px;height:640px;}}</style></head><body>
<div class="c"><svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg">{ICONS[icon]}</svg></div></body></html>"""


def sheet_html(paths: list[tuple[str, Path]]) -> str:
    """How the row looks on the profile: circles with names underneath."""
    items = "".join(f'<figure><div style="background-image:url({p.as_uri()})"></div><figcaption>{n.title()}'
                    f'</figcaption></figure>' for n, p in paths)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{bk.font_faces(FONTS)}
body{{margin:0;padding:48px 40px;width:1000px;background:#fff;font-family:Inter;display:flex;gap:28px;}}
figure{{margin:0;text-align:center;}} figure div{{width:132px;height:132px;border-radius:50%;background-size:100% auto;
background-position:center;box-shadow:0 0 0 3px #fff,0 0 0 5px {P['ink']['200']};}}
figcaption{{margin-top:12px;font-size:20px;color:{P['ink']['900']};}}</style></head><body>{items}</body></html>"""


def _page(html: str) -> str:
    f = OUT / "_page.html"
    f.write_text(html, encoding="utf-8")
    return f.as_uri()


def build() -> list[Path]:
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920})
        for name, icon, _ in HIGHLIGHTS:
            page.goto(_page(cover_html(icon)))   # a file:// page, so it may load the local fonts
            page.evaluate("document.fonts.ready")
            path = OUT / f"highlight-{icon}.png"
            page.screenshot(path=str(path))
            made.append((name, path))
        page = browser.new_page(viewport={"width": 1080, "height": 260})
        page.goto(_page(sheet_html(made)))
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(100)
        page.screenshot(path=str(OUT / "highlights-row.png"), full_page=True)
        browser.close()
    (OUT / "_page.html").unlink(missing_ok=True)
    (OUT / "highlights.json").write_text(json.dumps([{"name": n, "file": f"highlight-{i}.png", "holds": h}
                                                     for n, i, h in HIGHLIGHTS], indent=1), encoding="utf-8")
    return [p for _, p in made] + [OUT / "highlights-row.png"]


if __name__ == "__main__":
    for f in build():
        print(f"  ✓ {f.relative_to(ROOT)}")
