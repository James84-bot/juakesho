"""
picture.py — two plain measurements of a photo, used before it goes into a Reel.

near_same(): the same picture twice (two outlets running one press frame, or two stills of one video) wastes a
line of the Reel, so a second copy is dropped. A difference hash survives resizing, recompression and light crops.

detail(): how much of the photo's detail is real. A blurry TV still, or a small picture blown up by a website,
loses almost nothing when shrunk to half size and enlarged back; a sharp photo loses a lot. The score is that loss
measured against the loss at a fifth of the size (0-1, higher = sharper), so it does not depend on what the photo
shows. Measured on test photos: sharp ones score 0.38-0.57, the same photos enlarged 2x or blurred 0.16-0.25.

outlet_edit(): a picture a publisher has already designed (a "HEALTH" label, a headline, an inset circle, a logo, two
photos joined) is their edit, not a photograph; we never put our design on top of someone else's. A model that can
see answers it, once per picture (the verdicts are kept in state/photo_checks.json).
"""
from __future__ import annotations

import io

SOFT_BELOW = 0.30   # between the two groups above: under it, a picture is a soft copy
SAME_BITS = 10      # of 64: hashes this close are the same picture


def _gray(data: bytes, width: int | None = None):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        g = im.convert("L")
        if width and g.width > width:
            g = g.resize((width, max(8, round(g.height * width / g.width))), Image.LANCZOS)
        return g.copy()


def dhash(data: bytes) -> int | None:
    """64-bit difference hash: each bit says whether a pixel is brighter than its right-hand neighbour (9x8 grid).
    None if the bytes are not an image."""
    from PIL import Image
    try:
        g = _gray(data).resize((9, 8), Image.LANCZOS)
    except Exception:
        return None
    px = list(g.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (px[y * 9 + x] > px[y * 9 + x + 1])
    return bits


def near_same(a: int | None, b: int | None, max_bits: int = SAME_BITS) -> bool:
    return a is not None and b is not None and bin(a ^ b).count("1") <= max_bits


def detail(data: bytes) -> float:
    """0-1: how much detail survives only at full size (see the module note). 0.0 if the image can't be read."""
    try:
        import numpy as np
        from PIL import Image
        g = _gray(data, width=1600)   # a huge original is judged at the size we can show
        w, h = g.size
        ref = np.asarray(g, dtype=np.float32)

        def loss(f: float) -> float:
            small = g.resize((max(8, round(w * f)), max(8, round(h * f))), Image.LANCZOS)
            back = np.asarray(small.resize((w, h), Image.BICUBIC), dtype=np.float32)
            return float(np.mean(np.abs(ref - back)))

        total = loss(0.2)
        return round(loss(0.5) / total, 3) if total > 0.5 else 0.0   # a flat image has no detail to judge
    except Exception:
        return 0.0


def soft(data: bytes) -> bool:
    return detail(data) < SOFT_BELOW


EDIT_ASK = """You check pictures for a news page that only uses real, unedited photographs. Look at this image.
edited = true when a publisher or designer has added anything ON TOP of the photograph or combined pictures: words,
headlines, labels, category tags (NEWS, HEALTH) or captions laid over the image; a corner logo or watermark; a circle
or box with another picture inside; two or more photos joined side by side or stacked; a coloured band, border or
frame; icons, arrows or emoji; or the image is an illustration, chart, map or computer render.
Text that is physically in the scene does NOT count, however big or bright: signs, stage backdrops and banners
behind speakers, posters, name plates on a table, screens or projections in the room, printed clothing, packaging,
documents someone holds. Scene text sits on a surface: it follows the perspective and light of the room and people
or objects can stand in front of it. Added text is flat on top of everything, usually in a clean font or a box.
First write what text or graphics you see and what each one sits on, then decide.
Return ONLY JSON: {"seen": "under 30 words", "edited": true or false, "what": "what was added, under 12 words"}"""
CHECKS_KEEP = 400   # verdicts kept (the newest), enough for a week of photos from every outlet


def _checks_file():
    import brands
    return brands.STATE / "photo_checks.json"


def outlet_edit(data: bytes) -> str | None:
    """What a publisher added to this picture: '' for a plain photograph, the addition when it is their graphic,
    None when no model could look (logged; a missing check never costs a post its photo, and it is tried again
    next time). A "yes" from the cheap model is only believed when the stronger model agrees: in testing on 14 of
    our photos the cheap one alone took a monitor on a court wall and a plain skyline for added graphics."""
    import hashlib
    import json
    # the question is part of the key: when it changes, every picture is judged again under the new wording
    key = hashlib.sha1(data).hexdigest()[:24] + ":" + hashlib.sha1(EDIT_ASK.encode()).hexdigest()[:8]
    path = _checks_file()
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    if key in seen:
        return seen[key].get("what", "") if seen[key].get("edited") else ""
    import draft
    try:
        got = draft.extract_json(draft.look_at(data, EDIT_ASK))
        if got.get("edited") is True:
            second = draft.extract_json(draft.look_at(data, EDIT_ASK, strong=True))
            print(f"    edit check, second look: {'edited' if second.get('edited') is True else 'photo'} "
                  f"({str(second.get('seen') or '')[:140]})")
            if second.get("edited") is not True:
                got = second
    except Exception as e:   # no key, quota, or an unreadable reply
        print(f"    edit check skipped: {str(e)[:120]}")
        return None
    edited = got.get("edited") is True
    what = str(got.get("what") or "an edited graphic")[:80] if edited else ""
    print(f"    edit check: {'edited' if edited else 'photo'} ({str(got.get('seen') or '')[:140]})")
    seen[key] = {"edited": edited, "what": what}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(list(seen.items())[-CHECKS_KEEP:]), indent=0), encoding="utf-8")
    except OSError:
        pass
    return what
