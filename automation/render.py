"""
render.py — turns content/posts.json into finished Jua Kesho designs (PNG).

    python render.py                      # render everything in content/posts.json
    python render.py --only neno-ai       # render one post by id
    python render.py --file my_week.json  # render another content file
    python render.py --sheet              # also write a contact sheet of all renders

Each post names a template (templates/<name>.html.j2) and a background colour.
Shapes are generated from the post's seed, so every post gets its own
irregular composition, and re-rendering gives the identical image.

Requires: pip install jinja2 playwright  (then: playwright install chromium)
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import zlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape

import brandkit as bk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FONTS = (ROOT / "assets" / "fonts").as_uri()
LOGO = ROOT / "assets" / "logo"
OUT = ROOT / "exports"

SIZES = {
    "post": (1080, 1350),       # Instagram / Facebook / LinkedIn portrait
    "story": (1080, 1920),      # Stories, Reels/TikTok covers, WhatsApp Status
    "square": (1080, 1080),
    "youtube": (2560, 1440),
    "x": (1500, 500),
    "facebook": (1640, 624),
    "avatar": (1080, 1080),
}
DARK_BGS = {"usiku", "jacaranda", "chai", "shuka", "udongo"}


def fit(text: str, max_width: float, base: float, char_em: float = 0.78) -> int:
    """Largest font size (<= base) that keeps `text` within max_width in Unbounded ExtraBold."""
    longest = max((len(line) for line in str(text).split("\n")), default=1)
    return int(min(base, max_width / max(1, longest * char_em)))


def fitw(text: str, width: float, lines: int, base: float, char_em: float = 0.68) -> int:
    """Largest size (<= base) at which `text`, wrapped, fits in `lines` lines of `width` px (Unbounded ExtraBold)."""
    n = max(1, len(str(text)))
    return int(min(base, width * lines / (n * char_em)))


def arrow(x1, y1, x2, y2, color, width=7, bend=0.35) -> str:
    """Hand-drawn curved arrow from (x1, y1) to (x2, y2)."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    cx, cy = mx - dy * bend, my + dx * bend
    ang = math.atan2(y2 - cy, x2 - cx)
    head = 26
    a1, a2 = ang + math.radians(150), ang - math.radians(150)
    h1 = (x2 + math.cos(a1) * head, y2 + math.sin(a1) * head)
    h2 = (x2 + math.cos(a2) * head, y2 + math.sin(a2) * head)
    return (f'<path d="M{x1},{y1} Q{cx:.1f},{cy:.1f} {x2},{y2} M{h1[0]:.1f},{h1[1]:.1f} L{x2},{y2} '
            f'L{h2[0]:.1f},{h2[1]:.1f}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def radius(seed: int) -> str:
    """An irregular CSS border-radius, so text boxes look hand-cut instead of rounded rectangles."""
    rnd = random.Random(seed)
    h = [rnd.randint(18, 110) for _ in range(4)]   # horizontal radii, px
    v = [rnd.randint(18, 70) for _ in range(4)]    # vertical radii, px
    return " ".join(f"{x}px" for x in h) + " / " + " ".join(f"{y}px" for y in v)


COMIC = {"panel_top": [170, 520, 870], "panel_h": 330, "scale": 1.12, "spot": {"left": 185, "right": 895},
         "bubble_w": 360, "slot_a": 322, "slot_b": 322}


def comic_layout(panels: list[dict], width: int, seed: int) -> list[dict]:
    """Positions characters and speech bubbles for a 3-panel comic.

    Each side may have `say` (speech, tail to the head) and/or `sms`
    (dark phone bubble, tail to the phone). Slot A sits top-left of centre,
    slot B lower-right; a character's own speech takes the slot on its side.
    """
    out = []
    for i, p in enumerate(panels):
        top = COMIC["panel_top"][i]
        ground = top + COMIC["panel_h"] - 34
        chars, bubbles = [], []
        for side in ("left", "right"):
            c = p.get(side)
            if not c:
                continue
            x = COMIC["spot"][side]
            pose = c.get("pose", "stand") if c["who"] != "jua" else None
            if c["who"] == "jua":
                head = (x, ground - 100)
                phone = None
            else:
                j = bk.skeleton(x, ground, pose, COMIC["scale"])
                head = j["head"]
                phone = (j["r_hand"][0], j["r_hand"][1] - 14 * COMIC["scale"]) if c.get("sms") else None
            chars.append({**c, "x": x, "ground": ground, "pose": pose or "stand"})
            own, other = ("a", "b") if side == "left" else ("b", "a")
            if c.get("say"):
                bubbles.append({"text": c["say"], "sms": False, "slot": own, "target": head})
            if c.get("sms"):
                bubbles.append({"text": c["sms"], "sms": True, "slot": other, "target": phone})
        slots_used = [b["slot"] for b in bubbles]
        if len(slots_used) != len(set(slots_used)):
            raise ValueError(f"panel {i + 1}: at most one speech and one SMS bubble, from different sides")
        for b in bubbles:
            bw = COMIC["bubble_w"]
            if b["slot"] == "a":
                left, btop = COMIC["slot_a"], top + 40
            else:
                left, btop = width - COMIC["slot_b"] - bw, top + 142
            tx, ty = b["target"]
            ax = left + 10 if tx < left else left + bw - 10
            b.update(left=left, top=btop, radius=radius(seed + i * 7 + (1 if b["slot"] == "a" else 3)),
                     tail=(ax, btop + 22, tx + (26 if tx < left else -26), ty - 6, ax, btop + 62))
        out.append({"top": top, "bg": p["bg"], "chars": chars, "bubbles": bubbles})
    return out


def nobreak(text: str) -> Markup:
    """Keep hyphenated words (M-PESA, e-mail) on one line."""
    import re as _re
    return Markup(_re.sub(r"(\S+-\S+)", r'<span style="white-space:nowrap">\1</span>', str(escape(text))))


def _safe(fn):
    """Wrap an SVG-returning helper so Jinja inserts its markup unescaped."""
    return lambda *a, **k: Markup(fn(*a, **k))


def _grain_tile(size: int = 256, seed: int = 7) -> str:
    """A tileable noise PNG as a data URI (replaces a per-frame SVG turbulence filter)."""
    import base64
    import io

    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(seed)
    noise = rng.normal(128, 38, (size, size)).clip(0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(noise, "L").save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


GRAIN_URI = _grain_tile()


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    svg_helpers = {
        "blob": bk.blob, "blob_outline": bk.blob_outline, "squiggle": bk.squiggle, "kanga": bk.kanga_band, "dots": bk.dots,
        "leaf": bk.leaf, "confetti": bk.confetti, "mascot": bk.mascot, "arrow": arrow,
        "stick": bk.stick, "aurora": bk.aurora, "orbit": bk.orbit, "circuit": bk.circuit, "circuit_kanga": bk.circuit_kanga, "pixel_sun": bk.pixel_sun,
    }
    env.globals.update({k: _safe(v) for k, v in svg_helpers.items()})
    env.filters["nb"] = nobreak
    env.globals.update(GLOW=Markup(bk.GLOW_DEFS), comic_layout=comic_layout, C=bk.C, ON=bk.ON, fit=fit, fitw=fitw, radius=radius, brand=bk.BRAND)
    return env


def build_html(env: Environment, post: dict, motion: bool = False, reel: bool = False) -> str:
    kind = post.get("size", "post")
    W, H = SIZES[kind]
    bg_name = post.get("bg", "maziwa")
    dark = bg_name in DARK_BGS
    ctx = {
        **post,
        "W": W, "H": H,
        "bg": bk.C[bg_name], "bg_name": bg_name,
        "ink": bk.ON[bg_name], "dark": dark,
        "seed": int(post.get("seed", zlib.crc32(post["id"].encode()) % 10**6)),
        "colors": bk.C,
        "font_faces": Markup(bk.font_faces(FONTS)),
        "logo_on_light": (LOGO / "wordmark-on-light.svg").as_uri(),
        "logo_on_dark": (LOGO / "wordmark-on-dark.svg").as_uri(),
        "logo_stacked": (LOGO / "stacked-on-light.svg").as_uri(),
        "motion": motion, "reel": reel, "grain_uri": GRAIN_URI,
    }
    return env.get_template(f"{post['template']}.html.j2").render(**ctx)


QA_JS = """
() => {
  const canvas = document.getElementById('canvas').getBoundingClientRect();
  const skip = '.sticker, .stamp, .verdict, svg.mascot, .pnum, .save';
  const blocks = [...document.querySelectorAll('.layer > *, .foot')]
    .filter(el => !el.matches(skip))
    .map(el => ({ el, r: el.getBoundingClientRect() }))
    .filter(b => b.r.width > 2 && b.r.height > 2);
  const name = (el) => (el.className && el.className.baseVal === undefined ? el.className : el.tagName).toString().split(' ').slice(0, 2).join('.') || el.tagName;
  const issues = [];
  const tol = 6;
  for (const b of blocks) {
    const r = b.r;
    if (r.left < canvas.left - tol || r.top < canvas.top - tol || r.right > canvas.right + tol || r.bottom > canvas.bottom + tol)
      issues.push({ level: 'error', what: `'${name(b.el)}' runs off the canvas` });
    [b.el, ...b.el.querySelectorAll('*')].forEach(c => {
      if (c instanceof SVGElement || c.clientWidth === 0) return;
      if (c.scrollWidth > c.clientWidth + 4)
        issues.push({ level: 'error', what: `text wider than its box in '${name(b.el)}'` });
      if (getComputedStyle(c).overflow === 'hidden' && c.scrollHeight > c.clientHeight + 4)
        issues.push({ level: 'error', what: `text cut off at the bottom of '${name(b.el)}'` });
    });
  }
  for (let i = 0; i < blocks.length; i++) {
    for (let j = i + 1; j < blocks.length; j++) {
      const a = blocks[i].r, b = blocks[j].r;
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 8 && h > 8) {
        const area = w * h, small = Math.min(a.width * a.height, b.width * b.height);
        if (area > 0.04 * small)
          issues.push({ level: 'error', what: `'${name(blocks[i].el)}' collides with '${name(blocks[j].el)}' (${Math.round(w)}x${Math.round(h)}px)` });
      }
    }
  }
  return issues;
}
"""


def render(posts: list[dict], out_dir: Path, sheet: bool = False, qa: dict | None = None) -> list[Path]:
    from playwright.sync_api import sync_playwright

    env = make_env()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 2600, "height": 2000})
        for post in posts:
            html = build_html(env, post)
            tmp = out_dir / f".{post['id']}.html"
            tmp.write_text(html, encoding="utf-8")
            page.goto(tmp.as_uri())
            page.evaluate("document.fonts.ready")
            page.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => {})))")
            target = out_dir / f"{post['id']}.png"
            page.locator("#canvas").screenshot(path=str(target))
            issues = page.evaluate(QA_JS)
            if qa is not None:
                qa[post["id"]] = issues
            for i in issues:
                print(f"    ⚠ QA {post['id']}: {i['what']}")
            tmp.unlink()
            written.append(target)
            print(f"  ✓ {target.name}")
        browser.close()
    if sheet and written:
        contact_sheet(written, out_dir / "_contact-sheet.png")
    return written


def contact_sheet(files: list[Path], target: Path, col_w: int = 360, cols: int = 4) -> None:
    from PIL import Image

    thumbs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        thumbs.append(im.resize((col_w, int(im.height * col_w / im.width))))
    rows = [thumbs[i:i + cols] for i in range(0, len(thumbs), cols)]
    height = sum(max(t.height for t in r) + 16 for r in rows) + 16
    sheet = Image.new("RGB", (cols * (col_w + 16) + 16, height), "#2a2140")
    y = 16
    for r in rows:
        x = 16
        for t in r:
            sheet.paste(t, (x, y))
            x += col_w + 16
        y += max(t.height for t in r) + 16
    sheet.save(target)
    print(f"  ✓ {target.name}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Render Jua Kesho designs")
    ap.add_argument("--file", default=str(HERE / "content" / "posts.json"))
    ap.add_argument("--only", help="render a single post id")
    ap.add_argument("--out", default=None, help="output folder (default: exports/<collection>)")
    ap.add_argument("--sheet", action="store_true", help="write a contact sheet")
    args = ap.parse_args()

    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    posts = data["posts"]
    if args.only:
        posts = [p for p in posts if p["id"] == args.only]
        if not posts:
            print(f"No post with id '{args.only}'", file=sys.stderr)
            return 1
    out_dir = Path(args.out) if args.out else OUT / data.get("collection", "posts")
    print(f"Rendering {len(posts)} design(s) → {out_dir}")
    render(posts, out_dir, sheet=args.sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
