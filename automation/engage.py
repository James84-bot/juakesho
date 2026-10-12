"""
engage.py — answering comments, the way the biggest Kenyan accounts do: fast, short, in the people's voice,
with receipts. Every reply is drafted by the writer, checked by the guard, and approved by you on Telegram.

Runs with every tick (every 2 hours) once Instagram/Facebook are connected:
  1. fetch new comments on our recent posts (Instagram media + Facebook posts)
  2. sort them: reply (questions, pushback, good points), hide (hate, tribal insults, threats, spam), skip
  3. draft replies in batches, run them through the guard
  4. send each to Telegram: ✅ Reply  ⏭ Skip  🙈 Hide
  5. on ✅, post the reply under the comment; on 🙈, hide the comment (it stays visible to its author only)

Nothing is posted without your tap. Threats are flagged to you and never answered.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from html import escape as esc
from pathlib import Path

import guard

HERE = Path(__file__).resolve().parent
STATE_FILE = "comments.json"
MAX_NEW = 15            # comments considered per run (keeps AI calls and your Telegram calm)
LOOKBACK = dt.timedelta(days=7)
REPLY_MAX = 280

REPLY_RULES = """You answer comments for KENYANS ARE ASKING: informed ordinary Kenyans, not a media house. Reply the way
the best Kenyan accounts do: fast, short, warm, a bit of dry humour, in the commenter's language (English,
Kiswahili or Sheng). One to three short sentences, max 280 characters. Never corporate.

For each comment choose an action:
- "reply": a question (answer it with the fact and where to check it), a good point (thank them, add one fact,
  invite them to share), pushback or a wrong claim (calm correction with the receipt, never mocking the person),
  someone hurting (empathy first, then one practical step).
- "hide": tribal insults, hate against a group, sexual content, spam/scams, doxxing, calls to violence.
- "flag": threats against us or anyone, or anything needing a human (legal threats, a victim's private details).
- "skip": emoji-only, "first", plain agreement that needs nothing, bots.

Rules: never insult or name-call, never argue twice, never reveal who runs the page, never promise anything,
never tell anyone how to vote, no tribe ever. Facts only from the post's sources; if unsure, say where to check
instead of guessing. Sign nothing.
Return ONLY JSON: {"replies": [{"cid": "...", "action": "reply|hide|flag|skip", "reply": "...", "why": "..."}]}"""

HATE = re.compile(r"\b(kill (them|him|her|all)|madoadoa|kwekwe|cockroach(es)?|slaughter|burn (them|their))\b", re.I)


def state_path(state_dir: Path) -> Path:
    return state_dir / STATE_FILE


def load(state_dir: Path) -> dict:
    p = state_path(state_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"seen": [], "pending": {}}


def save(state_dir: Path, data: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    data["seen"] = data["seen"][-3000:]
    state_path(state_dir).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def recent_targets(weeks_dir: Path, now: dt.datetime) -> list[dict]:
    """Our published posts from the last week: where comments can be waiting."""
    out = []
    for f in sorted(weeks_dir.glob("*.json"))[-3:]:
        for p in json.loads(f.read_text(encoding="utf-8"))["posts"]:
            if p.get("status") != "published" or p.get("n"):
                continue
            when = dt.datetime.fromisoformat(p.get("published_at") or p["publish_at"])
            if now - when <= LOOKBACK:
                out.append(p)
    return out


def fetch(graph_get, posts: list[dict], own: set[str] = frozenset()) -> list[dict]:
    """New comments on Instagram media and Facebook posts, oldest first. Our own (the receipts) are left out."""
    found = []
    for p in posts:
        ctx = {"post_id": p["id"], "message": p.get("message", ""), "source": p.get("source", "")}
        if p.get("ig_id"):
            try:
                res = graph_get(f"{p['ig_id']}/comments", {"fields": "id,text,username,timestamp,from", "limit": 50})
                found += [{"cid": c["id"], "platform": "ig", "text": c.get("text", ""), "user": c.get("username", ""),
                           "time": c.get("timestamp", ""), **ctx} for c in res.get("data", [])
                          if (c.get("from") or {}).get("id") not in own]
            except Exception as e:
                print(f"  comments skipped (ig {p['id']}): {e}")
        if p.get("fb_id"):
            try:
                res = graph_get(f"{p['fb_id']}/comments", {"fields": "id,message,from,created_time", "limit": 50})
                found += [{"cid": c["id"], "platform": "fb", "text": c.get("message", ""),
                           "user": (c.get("from") or {}).get("name", ""), "time": c.get("created_time", ""), **ctx}
                          for c in res.get("data", []) if (c.get("from") or {}).get("id") not in own]
            except Exception as e:
                print(f"  comments skipped (fb {p['id']}): {e}")
    return sorted(found, key=lambda c: c["time"])


def check_reply(text: str) -> list[str]:
    """The guard for replies: clean, no name-calling, no campaigning, no AI tells, short."""
    probe = {"id": "reply-check", "template": "hack", "hook": "x", "title": "x", "moves": ["x", "y"], "payoff": text,
             "caption": "reply"}
    errs = [e for e in guard.check(probe).errors if "'payoff'" not in e]
    if len(text) > REPLY_MAX:
        errs.append(f"reply is {len(text)} chars (max {REPLY_MAX})")
    return errs


def draft(call, comments: list[dict]) -> list[dict]:
    """Asks the writer what to do with each comment. Obvious hate is hidden without asking the AI."""
    out, ask = [], []
    for c in comments:
        if HATE.search(c["text"]):
            out.append({**c, "action": "hide", "reply": "", "why": "hate or violence"})
        else:
            ask.append(c)
    for i in range(0, len(ask), 8):
        batch = ask[i:i + 8]
        payload = [{"cid": c["cid"], "comment": c["text"][:500], "on_post": c["message"], "post_sources": c["source"][:300]}
                   for c in batch]
        try:
            import draft as drafter
            got = drafter.extract_json(call(REPLY_RULES, json.dumps(payload, ensure_ascii=False), max_tokens=3000)).get("replies", [])
        except Exception as e:
            print(f"  reply drafts skipped: {e}")
            got = []
        by = {g.get("cid"): g for g in got}
        for c in batch:
            g = by.get(c["cid"]) or {"action": "skip", "reply": "", "why": "no draft"}
            action = g.get("action") if g.get("action") in {"reply", "hide", "flag", "skip"} else "skip"
            reply = str(g.get("reply") or "").strip()
            if action == "reply":
                errs = check_reply(reply)
                if errs:
                    action, g["why"] = "flag", "draft failed checks: " + "; ".join(errs)[:200]
            out.append({**c, "action": action, "reply": reply, "why": str(g.get("why", ""))[:200]})
    return out


def card(c: dict) -> tuple[str, str]:
    """Telegram text + buttons for one comment."""
    icon = {"reply": "💬", "hide": "🙈", "flag": "🚩"}[c["action"]]
    lines = [f"{icon} <b>{esc(c['platform'].upper())}</b> · @{esc(c['user'] or '?')} on <code>{esc(c['post_id'])}</code>",
             f"“{esc(c['text'][:400])}”"]
    if c["action"] == "reply":
        lines += ["", f"<b>Reply:</b> {esc(c['reply'])}"]
    else:
        lines += ["", f"<i>{esc(c['why'])}</i>"]
    buttons = []
    if c["action"] == "reply":
        buttons.append({"text": "✅ Reply", "callback_data": f"c|r|{c['cid']}"})
    buttons.append({"text": "🙈 Hide", "callback_data": f"c|h|{c['cid']}"})
    buttons.append({"text": "⏭ Skip", "callback_data": f"c|s|{c['cid']}"})
    return "\n".join(lines), json.dumps({"inline_keyboard": [buttons]})


def run(state_dir: Path, weeks_dir: Path, graph_get, call, send, now: dt.datetime, own: set[str] = frozenset()) -> int:
    """One engagement pass. Returns how many comments were sent to you.
    Only comment ids and the drafted reply are stored (the repo is public): no usernames, no comment text."""
    data = load(state_dir)
    seen = set(data["seen"])
    fresh = [c for c in fetch(graph_get, recent_targets(weeks_dir, now), own) if c["cid"] not in seen][:MAX_NEW]
    if not fresh:
        return 0
    sent = 0
    for c in draft(call, fresh):
        data["seen"].append(c["cid"])
        if c["action"] == "skip":
            continue
        text, buttons = card(c)
        send(text, buttons)
        data["pending"][c["cid"]] = {k: c[k] for k in ("platform", "reply", "post_id", "action")}
        sent += 1
    save(state_dir, data)
    return sent


def act(state_dir: Path, graph, action: str, cid: str) -> str:
    """Your tap on Telegram: post the reply, hide the comment, or skip."""
    data = load(state_dir)
    c = data["pending"].pop(cid, None)
    if not c:
        return "already handled"
    try:
        if action == "r" and c.get("reply"):
            if c["platform"] == "ig":
                graph(f"{cid}/replies", {"message": c["reply"]})
            else:
                graph(f"{cid}/comments", {"message": c["reply"]})
            result = "replied"
        elif action == "h":
            graph(cid, {"hide": "true"} if c["platform"] == "ig" else {"is_hidden": "true"})
            result = "hidden"
        else:
            result = "skipped"
    except Exception as e:
        data["pending"][cid] = c   # keep it so you can try again
        result = f"failed: {str(e)[:120]}"
    save(state_dir, data)
    return result


# ---------------------------------------------------------------------------
# Samples: see how the cards look before Instagram is connected. Nothing is stored or posted.
# ---------------------------------------------------------------------------
SAMPLE_COMMENTS = [
    ("ig", "wanjiku_ke", "Source ya hii story iko wapi? Msiongee tu bila proof"),
    ("fb", "Brian Otieno", "This is propaganda. Government imejenga barabara kila mahali, nyinyi mnaona tu mabaya"),
    ("ig", "kevo254", "Ningependa kujua, how do I check kama niko kwa register ya IEBC?"),
    ("fb", "Mama Shiro", "Hawa ni madoadoa tu, wafukuzwe"),
    ("ig", "user88213", "Nitawapata nyinyi watu, mnajua mnaongea na nani?"),
    ("ig", "nyambura.w", "🔥🔥🔥"),
]
SAMPLE_POST = {"post_id": "sample", "message": "Auditor-General: KSh billions spent on projects that were never finished. "
               "Ask your MP where your county's share went.",
               "source": "Office of the Auditor-General reports, oag.go.ke"}


def latest_post(weeks_dir: Path) -> dict:
    """Context for the samples: our newest post with a source, else a stand-in."""
    for f in sorted(weeks_dir.glob("*.json"), reverse=True):
        for p in reversed(json.loads(f.read_text(encoding="utf-8"))["posts"]):
            if p.get("source") and not p.get("n"):
                return {"post_id": p["id"], "message": p.get("caption") or p.get("hook") or "",
                        "source": p["source"]}
    return SAMPLE_POST


def samples(weeks_dir: Path, call, send) -> int:
    """Drafts real replies to made-up comments and sends the cards, marked SAMPLE. Taps do nothing."""
    ctx = latest_post(weeks_dir)
    comments = [{"cid": f"sample-{i}", "platform": pl, "user": u, "text": t, "time": str(i), **ctx}
                for i, (pl, u, t) in enumerate(SAMPLE_COMMENTS)]
    sent = 0
    for c in draft(call, comments):
        if c["action"] == "skip":
            continue
        text, buttons = card(c)
        send("🧪 <b>SAMPLE</b> (made-up comment, buttons do nothing)\n" + text, buttons)
        sent += 1
    return sent
