"""
quotes.py — people's exact words, taken from the report itself, never written by the model.

A news post delivers the message as it was said: when a report quotes someone ("...," Ruto said), the system reads
the article, lifts the words inside the quotation marks and the name the report gives the speaker, and keeps them on
the post (post["quotes"]). The writer may use one only word for word (a run of consecutive words from it, never
reworded, never joined to another), and guard.py checks every quoted span in a post against these: a quote that is
not in the report, character for character, fails.

    python quotes.py URL     # the quotes this system finds in one article
"""
from __future__ import annotations

import html as htmllib
import re
import sys

MIN_WORDS, MAX_WORDS = 5, 45   # a quote worth showing; a longer one is cut by the writer to a run of its words
SAID = (r"said|says|stated|states|noted|notes|added|adds|remarked|told|asked|asks|wrote|writes|declared|warned|"
        r"warns|explained|explains|insisted|insists|argued|argues|lamented|claimed|claims|charged|pleaded|urged|urges|"
        r"posed|stressed|indicated|observed|alleged|maintained|said in a statement|announced|announces")
NAME = r"(?:[A-Z][\w'’.\-]+\s){0,4}[A-Z][\w'’.\-]+"
NOT_NAMES = {"he", "she", "they", "it", "we", "i", "the", "this", "that", "his", "her", "their", "our", "who", "which",
             "statement", "report", "police", "government",
             # words that open a sentence before the speaker is named ("Asked when..., Mbadi said")
             "asked", "speaking", "addressing", "according", "but", "and", "however", "meanwhile", "while", "when",
             "in", "on", "at", "after", "before", "during", "earlier", "later", "yesterday", "today", "also"}
QUOTE = re.compile(r"[“\"]([^“”\"]{12,400})[”\"]")
PARA = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")


def paragraphs(page: str) -> list[str]:
    """The article's paragraphs as plain text (tags and entities resolved), in order."""
    out = []
    for raw in PARA.findall(page):
        text = re.sub(r"\s+", " ", htmllib.unescape(TAG.sub("", raw))).strip()
        if len(text) >= 30:
            out.append(text)
    return out


def _speaker(rest: str) -> str:
    """The name the report gives the speaker, from the words around the quote: "..., Ruto said" / "said Ruto" /
    "Ruto said: ..." ('' when the report only says "he said")."""
    for rx in (rf"^[\s,.;:–—-]*(?:{SAID})\s+({NAME})", rf"^[\s,.;:–—-]*({NAME})\s+(?:{SAID})\b",
               rf"({NAME})\s+(?:{SAID})\s*[:,]?\s*$", rf"({NAME}),?\s+(?:[a-z][\w\s,'-]{{0,60}}?),?\s+(?:{SAID})\s*[:,]?\s*$"):
        m = re.search(rx, rest)
        if m:
            name = m.group(1).strip(" ,.")
            if name.split()[0].lower() not in NOT_NAMES and len(name) >= 3:
                return name
    return ""


def from_text(paras: list[str]) -> list[dict]:
    """Every direct quote with a named speaker in these paragraphs: [{"text", "speaker"}]."""
    found = []
    for p in paras:
        for m in QUOTE.finditer(p):
            words = m.group(1).strip()
            n = len(words.split())
            if not MIN_WORDS <= n <= MAX_WORDS:
                continue
            after, before = p[m.end():m.end() + 80], p[max(0, m.start() - 120):m.start()]
            who = _speaker(after) or _speaker(before)
            if who:
                found.append({"text": words.rstrip(" ,"), "speaker": who})
    seen, out = set(), []
    for q in found:
        k = norm(q["text"])
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


def norm(text: str) -> str:
    """For comparing a quote with the report: same letters and words, whatever the quotation marks, apostrophes,
    dashes, spacing or the full stop at the end."""
    t = str(text or "").replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-").lower()
    t = re.sub(r"[“”\"*]", "", t)
    return re.sub(r"\s+", " ", t).strip(" .,;:!?")


def collect(post: dict, get=None, limit: int = 3) -> list[dict]:
    """The quotes in the post's own reports (its source links, at most `limit` pages), each with its outlet and
    link. A page that can't be read is skipped."""
    import posted
    get = get or (lambda url: posted._get(url, timeout=20))
    out = []
    for x in (post.get("source_links") or [])[:limit]:
        link = x.get("link") if isinstance(x, dict) else ""
        if not link:
            continue
        try:
            import gnews
            link = gnews.real_link(link)   # a Google News link: the newsroom's own article behind it
            page = get(link).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"    quotes: {x.get('outlet', '')} page not read ({str(e)[:60]})")
            continue
        for q in from_text(paragraphs(page)):
            out.append({**q, "outlet": x.get("outlet", ""), "link": link})
    return out[:12]


def spans(text: str) -> list[str]:
    """The quoted spans in our own text (3 words or more between quotation marks)."""
    return [m.group(1) for m in re.finditer(r"[“\"]([^“”\"]+)[”\"]", str(text or "")) if len(m.group(1).split()) >= 3]


def problem(text: str, quotes: list[dict]) -> str:
    """Why a quoted span in our text is not the speaker's exact words ('' when every one is a run of words from a
    quote the report printed)."""
    for s in spans(text):
        if "..." in s or "…" in s:
            return f'"{s[:50]}" joins words with an ellipsis: quote one run of the speaker\'s exact words'
        if not any(norm(s) and norm(s) in norm(q["text"]) for q in quotes):
            return (f'"{s[:60]}" is not word for word in the report: quote only the exact words the report printed'
                    + ("" if quotes else " (no quote was found in this story's reports)"))
    return ""


if __name__ == "__main__":
    import posted
    for q in from_text(paragraphs(posted._get(sys.argv[1], timeout=20).decode("utf-8", errors="replace"))):
        print(f"{q['speaker']}: “{q['text']}”")
