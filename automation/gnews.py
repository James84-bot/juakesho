"""
gnews.py — the newsroom's own article behind a Google News link.

Feeds that come through Google News (People Daily, the Nation, The Eastleigh Voice...) give links like
news.google.com/rss/articles/CBMi...; that page is Google's, not the article, so nothing in it can be quoted or
pictured. Google's own news page turns such a link into the article's address in two steps: its article page
carries a signature and a timestamp (data-n-a-sg, data-n-a-ts), and its "batchexecute" endpoint, given the
article id with them ("garturlreq"), answers with the address ("garturlres"). Answers are kept in
state/gnews_links.json, so a link is asked about once.

    python gnews.py https://news.google.com/rss/articles/CBMi...
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request

ARTICLE = "https://news.google.com/rss/articles/{id}?hl=en-US&gl=US&ceid=US:en"
BATCH = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
CTX = [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
       "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
KEEP = 600   # links remembered (the newest)


def article_id(url: str) -> str | None:
    u = urllib.parse.urlparse(str(url or ""))
    parts = u.path.split("/")
    if u.hostname == "news.google.com" and len(parts) > 1 and parts[-2] in {"articles", "read"}:
        return parts[-1] or None
    return None


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def _post(url: str, body: str) -> str:
    req = urllib.request.Request(url, data=body.encode(), method="POST",
                                 headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def body_for(art: str, ts: str, sig: str) -> str:
    inner = json.dumps(["garturlreq", CTX, art, int(ts) if str(ts).isdigit() else ts, sig], separators=(",", ":"))
    return "f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner, None, "generic"]]], separators=(",", ":")))


def parse_answer(text: str) -> str | None:
    """The article address in a batchexecute answer (')]}\\'' then rows: ["wrb.fr","Fbv4je","[\\"garturlres\\",url,...]"])."""
    body = text.split("\n\n", 1)[1] if "\n\n" in text else text
    body = body.lstrip()
    if body.startswith(")]}'"):
        body = body[4:].lstrip()
    try:
        rows = json.loads(body)
    except ValueError:
        return None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, list) and len(row) >= 3 and (row[0] == "wrb.fr" or row[1] == "Fbv4je") and isinstance(row[2], str):
            try:
                payload = json.loads(row[2])
            except ValueError:
                continue
            if isinstance(payload, list) and len(payload) > 1 and payload[0] == "garturlres":
                return str(payload[1])
    return None


def _cache_file():
    import brands
    return brands.STATE / "gnews_links.json"


def real_link(url: str, get=None, post=None) -> str:
    """The article's own address for a Google News link; any other link comes back as it is, and so does a
    Google link that could not be turned (the caller then has Google's page, which it ignores)."""
    art = article_id(url)
    if not art:
        return url
    path = _cache_file()
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    if art in seen:
        return seen[art]
    get, post = get or _get, post or _post
    try:
        page = get(ARTICLE.format(id=art))
        sg, ts = re.search(r'data-n-a-sg="([^"]+)"', page), re.search(r'data-n-a-ts="([^"]+)"', page)
        if not (sg and ts):
            return url
        found = parse_answer(post(BATCH, body_for(art, ts.group(1), sg.group(1))))
    except Exception as e:
        print(f"    google news link not turned: {str(e)[:80]}")
        return url
    if not found or not found.startswith("http"):
        return url
    seen[art] = found
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(list(seen.items())[-KEEP:]), indent=0), encoding="utf-8")
    except OSError:
        pass
    return found


if __name__ == "__main__":
    print(real_link(sys.argv[1]))
