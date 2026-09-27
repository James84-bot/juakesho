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
import re
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
    """Largest font size (<= base) that keeps every line of `text` (no wrapping) within max_width, Unbounded ExtraBold."""
    import textfit
    return min(textfit.fit_display(line, max_width, 1, base) for line in (str(text).split("\n") or [""]))


def fitw(text: str, width: float, lines: int, base: float, char_em: float = 0.68) -> int:
    """Largest size (<= base) at which `text` fits in `lines` lines of `width` px (Unbounded ExtraBold).
    Measured with the real font (textfit), so a long single word shrinks instead of spilling out.
    `char_em` is kept for old callers; it only matters for text the font file can't measure."""
    import textfit
    return textfit.fit_display(text, width, lines, base)


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


COMIC = {"panel_top": [158, 498, 838], "panel_h": 330, "scale": 1.12, "spot": {"left": 185, "right": 895},
         "bubble_w": 360, "slot_a": 322, "slot_b": 322, "a_top": 30, "b_top": 142, "gap": 12, "inset": 12}


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
        # Bubble heights come from the real font (textfit), so slot B always clears slot A,
        # and a panel whose lines cannot fit is rejected here, which the guard reports at draft time.
        import textfit
        bubbles.sort(key=lambda b: b["slot"])
        a_bottom = None
        limit = top + COMIC["panel_h"] - COMIC["inset"]
        for b in bubbles:
            bw = COMIC["bubble_w"]
            h = textfit.bubble_height(b["text"], b["sms"])
            if b["slot"] == "a":
                left, btop = COMIC["slot_a"], top + COMIC["a_top"]
                a_bottom = btop + h
            else:
                left = width - COMIC["slot_b"] - bw
                btop = max(top + COMIC["b_top"], (a_bottom or 0) + COMIC["gap"])
                if btop + h > limit:  # short first bubble: slot B may rise into the free space above
                    btop = max(top + COMIC["a_top"], (a_bottom or 0) + COMIC["gap"], limit - h)
            if btop + h > limit:
                raise ValueError(f"panel {i + 1}: the bubble text is too long to fit ({round(btop + h - limit)}px over); "
                                 "shorten the lines in this panel")
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


def build_html(env: Environment, post: dict, motion: bool = False, reel: bool = False, measure: bool = False) -> str:
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
    ink = post.get("ink") or {}
    ctx["ink_css"] = Markup("\n".join(
        ".layer" + "".join(f" > :nth-child({int(i)})" for i in path.split("/")) + f" {{ color: {col} !important; }}"
        for path, col in ink.items() if path and all(i.isdigit() for i in path.split("/")) and re.fullmatch(r"#[0-9A-F]{6}", col)))
    photo = post.get("photo_file")
    if photo and Path(photo).exists() and post["template"] in PHOTO_TEMPLATES:
        tones = ["jua", "pwani", "waridi", "shuka"]
        tone = post.get("photo_tone") if post.get("photo_tone") in bk.C else tones[ctx["seed"] % len(tones)]
        civic = post["template"] in {"money", "straight"} or post.get("series") in {"See Through It"}
        ctx.update(photo_uri=Path(photo).as_uri(), photo_tone=bk.C[tone],
                   photo_credit=("Illustrative photo · " if civic else "") + (post.get("photo_credit") or ""))
    import symbols
    sym = post.get("symbol") if post["template"] not in NO_SYMBOL and post.get("symbol") in symbols.SYMBOLS else ""
    person_file = post.get("person_file")
    if person_file and Path(person_file).exists() and post["template"] in PERSON_TEMPLATES:
        # A real person we celebrate: their real photo is the hero (the symbol steps aside)
        ctx["symbol"] = "portrait"
        ctx["person_credit"] = post.get("person_credit") or ""
        ctx.pop("photo_credit", None)   # one credit line: the person's photographer
        box = post.get("symbol_box")
        if measure or box:
            ctx["mascot"] = lambda *_a, **_k: Markup("")
        if box and not measure:
            ctx["symbol_box"], ctx["symbol_hero"] = box, Markup(symbols.portrait(Path(person_file).as_uri(), ctx["seed"]))
        return env.get_template(f"{post['template']}.html.j2").render(**ctx)
    ctx["symbol"] = sym   # templates switch to their hero-split layout when this is set
    if sym:
        if True:
            art = symbols.art(sym)
            # Giant faint silhouette behind the glass: the whole post reads as the idea at a glance
            if "photo_uri" not in ctx:   # a photo already fills the background
                ctx["symbol_ghost"] = Markup(symbols.ghost(sym, "#ffffff" if dark else bk.C["usiku"]))
            box = post.get("symbol_box")
            if measure or box:  # the hero symbol replaces the decorative mascot
                ctx["mascot"] = lambda *_a, **_k: Markup("")
            if box and not measure:
                ctx["symbol_box"], ctx["symbol_hero"] = box, Markup(art)
            elif not measure and post["template"] in SYMBOL_IN_MASCOT_SLOT:  # no room found: small, in the mascot's slot
                ctx["mascot"] = lambda *_a, **_k: Markup(f'<g transform="translate(9 9) scale(.455)">{art}</g>')
    return env.get_template(f"{post['template']}.html.j2").render(**ctx)


# Obstacles for symbol placement: text by its real line boxes (short lines leave room beside them),
# cards/pills/stickers by their full box, plus the footer.
OBSTACLES_JS = """
() => {
  const c = document.getElementById('canvas').getBoundingClientRect();
  const out = [];
  const add = (r) => { if (r.width > 1 && r.height > 1) out.push([r.left - c.left, r.top - c.top, r.right - c.left, r.bottom - c.top]); };
  const solid = (el) => {
    const s = getComputedStyle(el);
    const bg = s.backgroundColor, a = bg.startsWith('rgba') ? parseFloat(bg.split(',')[3]) : (bg === 'transparent' ? 0 : 1);
    return a > 0.02 || s.backdropFilter !== 'none' || parseFloat(s.borderTopWidth) > 0 || el instanceof SVGElement || el.tagName === 'IMG';
  };
  for (const el of document.querySelectorAll('.layer > *, .foot')) {
    if (el.matches('.symbol, svg.mascot')) continue;
    if (el.matches('.foot') || solid(el)) { add(el.getBoundingClientRect()); continue; }
    const range = document.createRange(); range.selectNodeContents(el);
    for (const r of range.getClientRects()) add(r);
    el.querySelectorAll('*').forEach(k => { if (solid(k)) add(k.getBoundingClientRect()); });
  }
  return {w: c.width, h: c.height, rects: out};
}
"""
SYMBOL = {"min": 150, "max": 420, "pad": 22, "margin": 40, "cell": 4}

# Legibility: every line of text vs the real pixels behind it (text fill hidden, shadows kept, since halos count)
TEXT_JS = """
() => {
  const c = document.getElementById('canvas').getBoundingClientRect();
  const out = [];
  const walker = document.createTreeWalker(document.querySelector('.layer'), NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.textContent.trim()) continue;
    const el = n.parentElement, cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    const m = cs.color.match(/[\\d.]+/g).map(Number);
    if (m.length > 3 && m[3] === 0) continue;
    if (el.closest('svg')) continue;   // SVG text is artwork (fills), checked by eye in the symbol sheet
    // Text on its own solid chip (sticker, stamp, pill): judge it against that colour, not the pixels around a tilted box
    let solid = null;
    for (let a = el; a && !a.classList.contains('layer'); a = a.parentElement) {
      const bg = getComputedStyle(a).backgroundColor.match(/[\\d.]+/g);
      if (bg && (bg.length < 4 || parseFloat(bg[3]) >= 0.9)) { solid = bg.slice(0, 3).map(Number); break; }
    }
    const rg = document.createRange(); rg.selectNodeContents(n);
    for (const r of rg.getClientRects()) {
      if (r.width < 6 || r.height < 6) continue;
      const path = []; for (let a = el; a && !a.classList.contains('layer'); a = a.parentElement) path.unshift([...a.parentElement.children].indexOf(a) + 1);
      out.push({text: n.textContent.trim().slice(0, 30), rgb: m.slice(0, 3), px: parseFloat(cs.fontSize), solid, path: path.join('/'),
                box: [r.left - c.left, r.top - c.top, r.right - c.left, r.bottom - c.top]});
    }
  }
  return out;
}
"""
HIDE_TEXT_CSS = ".layer, .layer * { color: transparent !important; -webkit-text-fill-color: transparent !important; text-decoration-color: transparent !important; }"


def _lum(rgb) -> float:
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


INK = ["jua", "pwani", "waridi", "maziwa", "white", "usiku"]   # adaptive ink candidates, brand accents first


def _ratio(a: float, b: float) -> float:
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _hex(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def adaptive_ink(page, texts: list[dict]) -> dict[str, str]:
    """For text that can't be read against what's behind it, the brand colour that reads best there.
    Keeps the designer's colour whenever it passes; returns {element path: css colour}."""
    fixes: dict[str, str] = {}
    for t, bgs in _backgrounds(page, texts):
        if t.get("solid") or not t.get("path"):
            continue   # text on its own chip: the chip's design decides
        need = 3.0 if t["px"] >= 24 else 4.5
        fg = _lum(t["rgb"])
        if min(_ratio(fg, b) for b in bgs) >= need:
            continue
        options = []
        for name in INK:
            rgb = (255, 255, 255) if name == "white" else _hex(bk.C[name])
            options.append((min(_ratio(_lum(rgb), b) for b in bgs), name, rgb))
        passing = [o for o in options if o[0] >= need]
        best = passing[0] if passing else max(options)
        # a path may carry several lines: keep the colour that works for all of them
        prev = fixes.get(t["path"])
        if prev is None or best[0] < need:
            fixes[t["path"]] = "#{:02X}{:02X}{:02X}".format(*best[2])
    return fixes


def _backgrounds(page, texts: list[dict]):
    import io
    import numpy as np
    from PIL import Image
    handle = page.add_style_tag(content=HIDE_TEXT_CSS)
    img = np.asarray(Image.open(io.BytesIO(page.locator("#canvas").screenshot())).convert("RGB")).astype(float)
    handle.evaluate("el => el.remove()")
    for t in texts:
        if t.get("solid"):
            yield t, [_lum(t["solid"])]
            continue
        l, tp, r, b = (int(max(0, v)) for v in t["box"])
        patch = img[tp:b, l:r]
        if patch.size == 0:
            continue
        lums = np.apply_along_axis(_lum, 1, patch.reshape(-1, 3)[:: max(1, patch.shape[0] * patch.shape[1] // 400)])
        yield t, list(np.percentile(lums, [10, 90]))


def contrast_issues(page, texts: list[dict]) -> list[dict]:
    """Screens the canvas with text fill hidden and checks each text line against the pixels behind it."""
    import io
    import numpy as np
    from PIL import Image
    handle = page.add_style_tag(content=HIDE_TEXT_CSS)
    img = np.asarray(Image.open(io.BytesIO(page.locator("#canvas").screenshot())).convert("RGB")).astype(float)
    handle.evaluate("el => el.remove()")
    issues, seen = [], set()
    for t in texts:
        fg = _lum(t["rgb"])
        if t.get("solid"):
            bgs = [_lum(t["solid"])]
        else:
            l, tp, r, b = (int(max(0, v)) for v in t["box"])
            patch = img[tp:b, l:r]
            if patch.size == 0:
                continue
            # the darkest-case and lightest-case backgrounds: text must read against 80% of what's behind it
            lums = np.apply_along_axis(_lum, 1, patch.reshape(-1, 3)[:: max(1, patch.shape[0] * patch.shape[1] // 400)])
            bgs = np.percentile(lums, [10, 90])
        worst = min((max(fg, bg) + 0.05) / (min(fg, bg) + 0.05) for bg in bgs)
        need = 3.0 if t["px"] >= 24 else 4.5
        key = t["text"]
        if worst < need and key not in seen:
            seen.add(key)
            issues.append({"level": "error" if worst < need * 0.72 else "warn",
                           "what": f"low contrast {worst:.1f}:1 (needs {need:.0f}:1) on '{key}'"})
    return issues


def free_square(w: int, h: int, rects: list, anchor: tuple[float, float] | None = None) -> list[int] | None:
    """Largest square (min..max px) that touches no obstacle; ties go to the spot nearest the anchor."""
    import numpy as np
    k, pad, m = SYMBOL["cell"], SYMBOL["pad"], SYMBOL["margin"]
    gw, gh = w // k, h // k
    occ = np.zeros((gh, gw), dtype=np.int32)
    for l, t, r, b in rects:
        x0, y0 = max(0, int((l - pad) // k)), max(0, int((t - pad) // k))
        x1, y1 = min(gw, int((r + pad) // k) + 1), min(gh, int((b + pad) // k) + 1)
        occ[y0:y1, x0:x1] = 1
    mk = m // k
    occ[:mk, :] = occ[-mk:, :] = 1
    occ[:, :mk] = occ[:, -mk:] = 1
    sat = np.pad(occ.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    ax, ay = anchor or (w * 0.74, h * 0.6)
    for size in range(SYMBOL["max"], SYMBOL["min"] - 1, -10):
        n = size // k
        if n > gw or n > gh:
            continue
        blocked = sat[n:, n:] - sat[:-n, n:] - sat[n:, :-n] + sat[:-n, :-n]
        ys, xs = np.nonzero(blocked == 0)
        if len(xs):
            cx, cy = (xs + n / 2) * k, (ys + n / 2) * k
            i = int(np.argmin((cx - ax) ** 2 + (cy - ay) ** 2))
            return [int(xs[i] * k), int(ys[i] * k), size]
    return None


def place_symbol(page, env: Environment, post: dict, tmp_dir: Path) -> None:
    """Lays the post out without its symbol, measures what landed where, and stores the best free square."""
    import symbols
    has_person = bool(post.get("person_file")) and post["template"] in PERSON_TEMPLATES and Path(post["person_file"]).exists()
    if not has_person and (not post.get("symbol") or post["template"] in NO_SYMBOL or post.get("symbol") not in symbols.SYMBOLS):
        return
    tmp = tmp_dir / f".{post['id']}-measure.html"
    tmp.write_text(build_html(env, post, measure=True), encoding="utf-8")
    page.goto(tmp.as_uri())
    page.evaluate("document.fonts.ready")
    m = page.evaluate(OBSTACLES_JS)
    tmp.unlink()
    box = free_square(int(m["w"]), int(m["h"]), m["rects"])
    if box:
        post["symbol_box"] = box
    else:
        post.pop("symbol_box", None)


# Layouts that celebrate a real person with their real photo (rights required: guard.py)
PERSON_TEMPLATES = {"spotlight"}
# Dark-background layouts that take a full-bleed photo (duotoned into the brand palette)
PHOTO_TEMPLATES = {"cover", "kesho", "spotlight", "money", "still", "straight", "hack", "decode", "build", "glasspoll"}
# Templates where Jua is a character in the scene (keep it), or that are brand assets
NO_SYMBOL = {"vichekesho", "pov", "avatar", "banner", "intro"}
# Templates whose mascot is decoration: a symbol replaces it in the same, collision-checked spot
SYMBOL_IN_MASCOT_SLOT = {"hack", "decode", "cap", "usiibiwe", "still", "glasspoll", "cover", "kesho", "tool",
                         "ukweli", "neno", "makanga", "shosh", "hapa", "poll", "africa"}


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
  // The hero symbol is checked against real text lines / solid boxes (the same way it was placed)
  const sym = document.querySelector('.layer > svg.symbol');
  if (sym) {
    const s = sym.getBoundingClientRect(), inset = s.width * 0.05;   // art keeps a 5% margin inside its box
    const S = {left: s.left + inset, top: s.top + inset, right: s.right - inset, bottom: s.bottom - inset};
    const solid = (el) => { const cs = getComputedStyle(el), bg = cs.backgroundColor;
      const a = bg.startsWith('rgba') ? parseFloat(bg.split(',')[3]) : (bg === 'transparent' ? 0 : 1);
      return a > 0.02 || cs.backdropFilter !== 'none' || parseFloat(cs.borderTopWidth) > 0 || el instanceof SVGElement || el.tagName === 'IMG'; };
    for (const b of blocks) {
      if (b.el === sym) continue;
      let rects = [];
      if (b.el.matches('.foot') || solid(b.el)) rects = [b.r];
      else { const rg = document.createRange(); rg.selectNodeContents(b.el); rects = [...rg.getClientRects()];
             b.el.querySelectorAll('*').forEach(k => { if (solid(k)) rects.push(k.getBoundingClientRect()); }); }
      for (const r of rects) {
        const w = Math.min(r.right, S.right) - Math.max(r.left, S.left), h = Math.min(r.bottom, S.bottom) - Math.max(r.top, S.top);
        if (w > 6 && h > 6) { issues.push({ level: 'error', what: `symbol covers '${name(b.el)}' (${Math.round(w)}x${Math.round(h)}px)` }); break; }
      }
    }
  }
  for (let i = 0; i < blocks.length; i++) {
    if (blocks[i].el === sym) continue;
    for (let j = i + 1; j < blocks.length; j++) {
      if (blocks[j].el === sym) continue;
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
            place_symbol(page, env, post, out_dir)
            tmp = out_dir / f".{post['id']}.html"
            post.pop("ink", None)
            for attempt in range(2):   # lay out, fix unreadable ink, lay out again with the fixes
                tmp.write_text(build_html(env, post), encoding="utf-8")
                page.goto(tmp.as_uri())
                page.evaluate("document.fonts.ready")
                page.evaluate("Promise.all([...document.images].map(i => i.decode().catch(() => {})))")
                if attempt:
                    break
                fixes = adaptive_ink(page, page.evaluate(TEXT_JS))
                if not fixes:
                    break
                post["ink"] = fixes
            target = out_dir / f"{post['id']}.png"
            page.locator("#canvas").screenshot(path=str(target))
            issues = page.evaluate(QA_JS) + [i for i in contrast_issues(page, page.evaluate(TEXT_JS)) if i["level"] == "error"]
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
