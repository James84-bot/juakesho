"""
picture.py — two plain measurements of a photo, used before it goes into a Reel.

near_same(): the same picture twice (two outlets running one press frame, or two stills of one video) wastes a
line of the Reel, so a second copy is dropped. A difference hash survives resizing, recompression and light crops.

detail(): how much of the photo's detail is real. A blurry TV still, or a small picture blown up by a website,
loses almost nothing when shrunk to half size and enlarged back; a sharp photo loses a lot. The score is that loss
measured against the loss at a fifth of the size (0-1, higher = sharper), so it does not depend on what the photo
shows. Measured on test photos: sharp ones score 0.38-0.57, the same photos enlarged 2x or blurred 0.16-0.25.
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
