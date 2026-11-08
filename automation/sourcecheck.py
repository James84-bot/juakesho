"""
sourcecheck.py — can the runner read the official pages a brand is built on? One request each: the HTTP status,
the size, the page title, and (for data pages) whether the expected words are on it. Reads only; posts nothing.

    python sourcecheck.py            # every source below
"""
from __future__ import annotations

import re
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

SOURCES = [   # (brand, what, url, words expected on the page)
    ("shillingbrief", "CBK exchange rates", "https://www.centralbank.go.ke/rates/forex-exchange-rates/", "US DOLLAR"),
    ("shillingbrief", "CBK T-bill results", "https://www.centralbank.go.ke/securities/treasury-bills/", "91"),
    ("shillingbrief", "CBK central bank rate", "https://www.centralbank.go.ke/rates/central-bank-rate/", "Rate"),
    ("shillingbrief", "CBK inflation", "https://www.centralbank.go.ke/inflation-rates/", "Inflation"),
    ("shillingbrief", "CBK home", "https://www.centralbank.go.ke/", "Central Bank"),
    ("shillingbrief", "EPRA pump prices", "https://www.epra.go.ke/pump-prices", "Super"),
    ("shillingbrief", "EPRA home", "https://www.epra.go.ke/", "EPRA"),
    ("shillingbrief", "KNBS", "https://www.knbs.or.ke/", "KNBS"),
    ("shillingbrief", "NSE", "https://www.nse.co.ke/", "NSE"),
    ("shillingbrief", "Gold price API", "https://api.gold-api.com/price/XAU", "price"),
    ("verifiedjobske", "PSC vacancies", "https://www.publicservice.go.ke/index.php/recruitment/vacancies", "Vacanc"),
    ("verifiedjobske", "PSC home", "https://www.publicservice.go.ke/", "Public Service"),
    ("verifiedjobske", "MyGov", "https://www.mygov.go.ke/", "MyGov"),
    ("verifiedjobske", "KUCCPS", "https://www.kuccps.ac.ke/", "KUCCPS"),
    ("verifiedjobske", "HELB", "https://www.hef.co.ke/", "HELB"),
    ("verifiedjobske", "TSC", "https://www.tsc.go.ke/", "Teachers"),
    ("verifiedjobske", "KDF recruitment", "https://www.mod.go.ke/recruitment/", "Recruit"),
    ("verifiedjobske", "Kenya Power careers", "https://www.kplc.co.ke/content/item/40/careers", "Career"),
]


def check(url: str, words: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(600_000)
            text = body.decode("utf-8", "replace")
            title = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
            return {"status": r.status, "bytes": len(body), "final": r.geturl(),
                    "title": re.sub(r"\s+", " ", title.group(1)).strip()[:80] if title else "",
                    "found": words.lower() in text.lower()}
    except Exception as e:
        return {"status": getattr(e, "code", None) or "error", "error": str(e)[:120]}


def run() -> list[str]:
    lines = []
    for brand, what, url, words in SOURCES:
        r = check(url, words)
        if "error" in r:
            lines.append(f"{brand} | {what} | {r['status']} | {r['error']}")
        else:
            lines.append(f"{brand} | {what} | {r['status']} | {r['bytes']} B | '{words}' {'found' if r['found'] else 'NOT found'}"
                         f" | {r['title']} | {r['final'][:90]}")
    return lines


if __name__ == "__main__":
    for line in run():
        print(line)


def tables(url: str, max_rows: int = 12) -> list[str]:
    """The text of each table on a page, row by row (for writing a parser against the real page)."""
    import html as h
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        page = r.read().decode("utf-8", "replace")
    out = []
    for t, table in enumerate(re.findall(r"<table[^>]*>(.*?)</table>", page, re.S | re.I)):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)[:max_rows]:
            cells = [h.unescape(re.sub(r"<[^>]+>", " ", c)).split() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S | re.I)]
            out.append(f"t{t}: " + " | ".join(" ".join(c) for c in cells))
    if not out:
        out.append("no tables; links: " + " ".join(re.findall(r'href="([^"]+\.(?:pdf|xlsx?|csv))"', page, re.I)[:15]))
    return out
