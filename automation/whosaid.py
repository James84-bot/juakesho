"""
whosaid.py — "Who said it?": a weekly quiz Reel built from the exact words Kenyan newsmakers said this week.

Line 1 is the quote, big, under "Who said it?", over a blurred picture of the speaker. Line 2 is a clue from the
report's own paragraph (a role or a place, never a name). Line 3 asks for guesses in the comments. Line 4 reveals the
speaker with their face, sharp. People comment before the end and watch to the end: both lift a Reel.

Only words a report printed as a direct quote (quotes.py collects them, guard.py checks them word for word), at most
14 of them, said by a named person. Never a quote from a post that carries an allegation (no face beside one).
A quote is used once (state/whosaid.json).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
from pathlib import Path

import brands

WINDOW = dt.timedelta(days=7)
MIN_WORDS, MAX_WORDS = 6, 14
USED = brands.STATE / "whosaid.json"
SERIES = "Who said it?"

PICK = """You pick this week's "Who said it?" quiz for a Kenyan news page (18-30 year olds).
Below are exact quotes from this week's reports, each with its speaker and the report's own paragraph.
Pick the ONE Kenyans would most want to guess: punchy, about something people talked about, and clear on its own.
Then write a clue of at most 12 words, one complete plain sentence, taken ONLY from that report's paragraph: the
speaker's role or where they said it, as the report states it. Never their name, initials, nickname or party, and
never guess a role the paragraph does not state. If no quote is worth a quiz, pick -1.
Return ONLY JSON: {"pick": <index>, "clue": "..."}"""


def _used() -> set[str]:
    try:
        return set(json.loads(USED.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _key(words: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", words.lower()).strip()[:120]


def remember(words: str) -> None:
    done = sorted(_used() | {_key(words)})[-200:]
    brands.STATE.mkdir(parents=True, exist_ok=True)
    USED.write_text(json.dumps(done, indent=1), encoding="utf-8")


def full_name(speaker: str, texts: list[str], lookup: bool = False) -> str:
    """'Gachagua' -> 'Rigathi Gachagua' when the post or the report names him so; '' for a body ('KNBS', 'AIU') or a
    surname nobody spells out (a face search by surname alone finds the wrong people)."""
    import photos
    def plain(w: str) -> bool:   # a name word: not a title, not a body ('Treasury CS Mbadi')
        return w.lower() not in photos.TITLES | {"mr", "mrs", "ms", "dr"} and not photos.INSTITUTION.match(w.lower())
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’-]+", speaker or "") if plain(w)]
    if not words:
        return ""
    sur = words[-1]
    if sur.isupper() or not sur[0].isupper():
        return ""
    if len(words) >= 2 and words[-2][0].isupper():
        return f"{words[-2]} {sur}"
    for t in texts:   # 'John Mbadi' for Mbadi; 'Kalonzo Musyoka' for Kalonzo (the news calls some by first name)
        t = str(t or "")
        for m in re.finditer(rf"\b([A-Z][a-z'’-]{{2,}})\s+{re.escape(sur)}\b", t):
            if plain(m.group(1)):
                return f"{m.group(1)} {sur}"
        for m in re.finditer(rf"\b{re.escape(sur)}\s+([A-Z][a-z'’-]{{2,}})\b", t):
            if plain(m.group(1)):
                return f"{sur} {m.group(1)}"
    return wikidata_name(sur) if lookup else ""


def wikidata_name(word: str, get=None) -> str:
    """The Kenyan public figure Wikidata knows by this name, when exactly one person it lists has it in their name
    and a Kenyan description ('Gachagua' -> 'Rigathi Gachagua'); '' when none or several do (no guessing)."""
    import socialpics
    get = get or socialpics._get_json
    q = {"action": "wbsearchentities", "search": word, "language": "en", "type": "item", "limit": 10, "format": "json"}
    try:
        found = get("https://www.wikidata.org/w/api.php?" + __import__("urllib.parse").parse.urlencode(q)).get("search", [])
    except Exception:
        return ""
    names = {str(x.get("label") or "") for x in found
             if re.search(r"\bKenya", str(x.get("description") or "")) and re.search(r"politician|leader|president|minister|"
                                                                                r"governor|senator|footballer|coach|athlete|"
                                                                                r"musician|singer|lawyer|judge|journalist",
                                                                                str(x.get("description") or ""), re.I)
             and re.search(rf"\b{re.escape(word)}\b", str(x.get("label") or ""))}
    names = {n for n in names if len(n.split()) >= 2}
    return names.pop() if len(names) == 1 else ""


def excerpt(text: str) -> str:
    """The quote, or its opening sentence, or its opening clause: the first of these that is 6-14 words, word for
    word ('' if none is). A longer quote opens with its point ('We came to the IEBC today in good faith, and we
    expected the same in return...'); cutting at a sentence or a comma keeps the words exactly as said."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    clause = re.split(r"[,;:—–]\s", sentence, maxsplit=1)[0]
    if DEPENDENT.match(clause):   # 'When a player is called up for Kenya' needs the rest of its sentence
        clause = ""
    for cut in (text, sentence, clause):
        cut = cut.strip().rstrip(".,;:")
        if MIN_WORDS <= len(cut.split()) <= MAX_WORDS:
            return cut
    return ""


DEPENDENT = re.compile(r"\s*(when|if|because|although|though|while|as|since|unless|until|after|before|once|whether|"
                       r"so that|in order to|which|who|that)\b", re.I)


def candidates(posts: list[dict], now: dt.datetime, used: set[str] | None = None, lookup: bool = False) -> list[dict]:
    """This week's quotes that can make a quiz, newest post first. With `lookup`, a speaker the reports name by one
    word only is looked up on Wikidata (wikidata_name)."""
    import photos
    used = _used() if used is None else used
    out, seen = [], set()
    for p in sorted(posts, key=lambda x: str(x.get("drafted_at") or ""), reverse=True):
        try:
            when = dt.datetime.fromisoformat(str(p.get("drafted_at")))
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=now.tzinfo)
        if not p.get("hot") or not p.get("quotes") or now - when > WINDOW or photos._accused(p):
            continue
        texts = [p.get("who"), p.get("message"), " ".join(map(str, p.get("beats") or [])), p.get("caption")]
        for q in p["quotes"]:
            words = excerpt(str(q.get("text") or ""))
            if not words or _key(words) in used or _key(words) in seen:
                continue
            name = full_name(str(q.get("speaker") or ""), [q.get("context")] + texts, lookup=lookup)
            if not name:
                continue
            seen.add(_key(words))
            title = next((str(x.get("title") or "") for x in p.get("source_links") or []
                          if isinstance(x, dict) and x.get("link") == q.get("link")), "")
            out.append({"speaker": q.get("speaker"), "name": name, "words": words, "outlet": q.get("outlet", ""),
                        "link": q.get("link", ""), "title": title, "context": str(q.get("context") or "")[:600],
                        "post": p["id"], "quote": q})
    return out


def clue_problem(clue: str, c: dict) -> str:
    """Why a clue can't be used ('' if it can): too long, not a sentence, or it gives the name away."""
    text = str(clue or "").strip()
    if not text or len(text.split()) > 12:
        return "a clue is 1-12 words"
    if not text.endswith((".", "!")):
        return "a clue is a complete sentence"
    names = {w.lower() for w in re.findall(r"[A-Za-z'’-]{3,}", f"{c['name']} {c['speaker']}")}
    if names & {w.lower() for w in re.findall(r"[A-Za-z'’-]{3,}", text)}:
        return "the clue names the speaker"
    return ""


def choose(cands: list[dict], call) -> tuple[dict, str] | None:
    """The writer's pick and its clue, checked; None when it picks nothing or its clue gives the answer away."""
    import draft
    listed = "\n".join(f'[{i}] {c["speaker"]}: “{c["words"]}”\n    the report: {c["context"][:400]}'
                       for i, c in enumerate(cands[:12]))
    got = draft.extract_json(call(PICK, listed, max_tokens=600))
    i = got.get("pick")
    if not isinstance(i, int) or not 0 <= i < min(len(cands), 12):
        return None
    clue = str(got.get("clue") or "").strip()
    if clue_problem(clue, cands[i]):
        return None
    return cands[i], clue


def mystery(face: bytes) -> bytes:
    """The speaker's picture blurred and darkened: a shape to guess from, not a face to read."""
    from PIL import Image, ImageEnhance, ImageFilter
    with Image.open(io.BytesIO(face)) as im:
        im = im.convert("RGB")
        im = im.filter(ImageFilter.GaussianBlur(max(im.size) / 16))
        im = ImageEnhance.Brightness(im).enhance(0.62)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def post_for(c: dict, clue: str, pid: str, publish_at: str, face: dict, out_dir: Path, now: dt.datetime) -> dict:
    """The quiz post, its two pictures saved in out_dir (the blurred one leads, the sharp one is the reveal)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sharp = Path(face["file"])
    blur = out_dir / f"{pid}-mystery.jpg"
    blur.write_bytes(mystery(sharp.read_bytes()))
    words = c["words"]
    return {
        "id": pid, "template": "whosaid", "series": SERIES, "reel": True, "hand": True, "whosaid": True,
        "bg": "usiku", "lane": "everyone", "size": "post", "kicker": SERIES, "quote": words,
        "beats": [f"{SERIES}: “{words}”", clue, "Drop your guess in the comments before the reveal.",
                  f"{c['name']}: “{words}”"],
        "shot_seq": [0, 0, 0, 1],
        "caption": "Who said it this week? Comment your guess, then watch to the end for the answer. Share it with "
                   "the friend who always knows.\n\n#WhoSaidIt #KenyaOnRecord",
        "quotes": [c["quote"]],
        "source": f"{c['outlet']}: {c['link']}" + (f"\nPhoto: {face.get('credit')}" if face.get("credit") else ""),
        "source_links": [{"outlet": c["outlet"], "link": c["link"], "title": c.get("title", "")}],
        "photo_file": str(blur), "photo_credit": "", "photo_kind": face.get("kind", "file"),
        "extra_photos": [str(sharp)], "shot_info": [{}, {"credit": face.get("credit", "")}],
        "quiz_answer": c["name"], "quiz_from": c["post"],
        "publish_at": publish_at, "status": "drafted", "drafted_at": now.isoformat(timespec="seconds"),
    }


def face_for(c: dict, pid: str, out_dir: Path) -> dict | None:
    """A picture that shows the speaker (photos.fetch with the speaker as the story's person, so the lead picture
    must show them)."""
    import photos
    probe = {"id": f"{pid}-face", "template": "sauti", "hot": True, "who": c["name"],
             "message": f"{c['name']} said: {c['words']}", "beats": [f"{c['name']} said this week."],
             "drafted_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    return photos.fetch(probe, out_dir)
