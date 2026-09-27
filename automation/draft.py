"""
draft.py — the AI writer. Fills a planned week with posts in the Jua Kesho voice.

Uses the Anthropic Messages API over plain HTTPS (no SDK needed).
Environment:
    ANTHROPIC_API_KEY   required for real drafting
    JUA_MODEL           model id (default below; override when newer models ship)

Every draft is run through guard.py. If the guard finds errors, the model gets
one repair pass with the exact errors. Anything still failing is marked
`needs_human` and never auto-renders.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import guard

HERE = Path(__file__).resolve().parent
API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5"   # override with JUA_MODEL; see platform.claude.com/docs/en/models/overview

BRAND_RULES = """You write for JUA KESHO, a faceless Kenyan content brand (NOT a school) for young, social-media-native
people (roughly 17-30): sharp, educated, online all day, but not yet tapping into AI and the future.
Friends on every continent are welcome too. We make them the first in their circle to know.
Mascot: Jua, a cheerful sun. Community: the Wanakesho ("people of tomorrow").
Tagline: "Kesho iko hapa." (Tomorrow is here.)

VOICE
- Kenyan English: natural, warm, the way Kenyans actually talk ("Eh!", "sasa", "kindly", "manze", "sawa",
  "pole", "even mama mboga..."). Everyday Kenyan words are welcome; whole sentences stay in English so
  anyone in Kenya or abroad can follow. Brand terms stay Swahili: Jua Kesho, Wanakesho, Usiibiwe!, Kesho Kutwa, Vichekesho.
- Funny through situations and analogies (matatu, M-Pesa, mama mboga, Shosh), never by mocking people.
- Simple words, short sentences, one idea per post. Practical: the reader can do something today.
- Hopeful about the future and honest about risks.

CLEAN FOR EVERYONE (hard rules)
- No swearing or insults in any language. Nothing sexual, no alcohol or drugs.
- No politics, politicians, tribes, religion debates, betting, get-rich-quick, or crypto promotion.
- Never shame poverty, age, gender, region or education. Elites and people with nothing both feel welcome.

FACTS
- Only state facts you are confident are true. Prefer timeless facts over statistics.
- Any post with a year, number, percentage, price or claim about a company MUST include a "source"
  (a URL or a precise description of where to verify). If unsure, drop the fact.
- Predictions are phrased as likely, not certain.

WHAT TRENDS (researched, 2026)
- The first line is the hook: 7 words max, a pattern interrupt, curiosity or a bold claim. It must work in under 2 seconds.
- Design for SENDS: DM shares weigh far more than likes for reaching new people. Ask "who would send this to whom?"
  and write for that moment ("send this to your friend who...").
- Saves come from genuinely useful posts (hacks, steps, prompts). Comments come from takes people want to argue with.
- Carousels: slide 1 ends on a cliffhanger that forces a swipe. Last slide asks for a send or save.
- Put searchable keywords in the title and caption (people search TikTok/IG like Google).
- Everything original. No reposts, no watermarks. Edutainment: teach one thing, make it fun.

CRITIQUE WITHOUT CRUELTY
- Roast outdated systems, habits, processes and bad tech ("Still in 2026?"). Never roast a person, a named
  artist, a group, a region or a politician. No "stupid", no "Africans are...". The joke is on the old way.
- Always pair the roast with the upgrade that exists today.
- "Africans don't support their own" is answered with ACTION: "Put Us On" spotlights of real African artists,
  creators and startups. Positive only, facts sourced, and give people something to do (stream, follow, share).

SEE THROUGH IT (civic truth, told symbolically)
- In scope: public money and stalled projects, paid disinformation and bought trends, hired crowds ("goons"),
  people who exploit faith for money or control, powerful people taking advantage of ordinary Kenyans.
- Target SYSTEMS and TACTICS, never a named person, party, tribe or church. Villains are fictional archetypes
  (Bwana Ahadi, "Mr Promise"). Never draw or describe anyone to resemble a real person.
- Every number from a named public source (Auditor-General, Controller of Budget, peer-reviewed research,
  reputable media) in `source`. If you can't source it, don't say it.
- Faith: never attack belief or believers. Expose manipulation tactics (pay-for-a-miracle, isolation from family,
  fear and urgency, "stop your medicine") so believers can protect each other.
- Tribe: never, in any direction. Our unity is the point: Kenyan English and Sheng belong to everyone.
- Always end with a legal, constructive action: read the report, verify before sharing, report the scam, build.
- Use the AI Hack template with `series`: "See Through It" for manipulation-literacy posts, and `money` for public money.

TONES TOOLBOX (use every one of them, on purpose)
- Sarcasm & deadpan: "Only Sh304bn idle. Minor." Works because the fact underneath is real and sourced.
- Irony & exaggeration: "It's 2026 and we still queue for 4 hours to be told 'come tomorrow'."
- Parody: fake ads, fake product launches, mock awards ("Introducing The Queue™, now with extra waiting").
  Parody must be unmistakable (label it: "parody", "not a real ad") so it never becomes misinformation.
- Hype & celebration: go loud for African wins (Put Us On).
- Warmth: sincere when someone could get hurt (Usiibiwe!, faith exploitation).
- Rules: punch UP (systems, tactics, the powerful, outdated habits), never down (victims, the poor, ordinary
  people, groups). Sarcasm about a situation, never about a named person.

MANIFESTO: Africa can't wait. Wake up, build, do it right. Energy, never despair.

EVERY INDUSTRY
- Rotate through music, sports, fashion, film, money, gaming, food, farming, beauty and campus life, always through
  the tech or future angle (AI in music production, data in football, online selling in fashion...).

BRAND AS FANDOM
- Jua and the stick cast are characters with lore. Keep running jokes going week to week.
- Platform-native humour: self-aware, a little unhinged, never mean, never dirty.
- Lo-fi relatable beats polished. Real builds (Build With Me) beat stock advice.
- Values in action: Usiibiwe! protects people; free for everyone.

MAKE THEM WANT MORE (every week)
- Rituals: each series owns its day. Mention it ("Kila Jumatatu ni Neno la Wiki").
- Open loops: every caption teases the next post or next week ("Kesho: ...", "Jumamosi tunafunua...").
- Carousels end on a cliffhanger slide or a question that the next post answers.
- Collecting: Neno la Wiki words are numbered entries in "Kamusi ya Kesho" (the community dictionary).
- Participation: invite replies that shape future posts (vote the next word, send Shosh a question).
- Payoff: every post teaches one thing the reader can use or share today. No empty hype.

CAPTIONS
- 1 to 4 short lines, ends with a question or a clear action (save, share, tag, reply).
- Max 3 hashtags; always include #JuaKesho plus the series tag.
"""

SERIES = {
    "neno": "Word of the Week: one tech word explained. `word` short (ideally an acronym or single word). "
            "`sw` = the simple definition, `en` = a second line that corrects a common misunderstanding. Number it in the caption (No. N).",
    "tool": "Today's Tool: a free tool or phone feature, 2-4 steps anyone can follow today.",
    "usiibiwe": "Usiibiwe!: a real, common scam pattern in Kenya and how to spot it. `sender` masked like +254 7XX XXX XXX.",
    "shosh": "Shosh Asks: Grandma asks a funny-but-real question, Jua answers kindly and clearly.",
    "makanga": "Makanga Explains: a tech idea explained as a matatu/stage analogy. `like` completes 'X is like...'.",
    "ukweli": "True or Fake?: a popular belief, a verdict (uongo = fake | ukweli = true | kiasi = partly) and the truth. "
              "`verdict_text` is the stamp, e.g. FAKE, TRUE, NOT QUITE.",
    "africa": "Made in Africa: a real African innovation with its year and country. Needs source.",
    "hapa": "Here vs There: how something works in Kenya vs elsewhere, friendly and curious, ends with a question to the world.",
    "cover": "Kesho Kutwa carousel cover: `series` = 'Kesho Kutwa', `lines` 2-4 short lines, `highlight` index.",
    "kesho": "Kesho Kutwa slide: one near-future change: `leo` (what exists today), `kesho` (what's coming), `anza` (try it now).",
    "poll": "Jua Asks story poll: a question anyone can answer with 2 options.",
    "money": "Follow the Money: one public-money number (`number` short like Sh304bn), `unit`, `what` it is, `why` it matters to a young person, `check` how to verify it themselves. Source required.",
    "hack": "AI Hack (or `series`: 'See Through It' for manipulation literacy): one move that saves real time, levels up a skill, or helps you see through a trick. `hook` 7 words max, `moves` 2-4 concrete steps, `payoff` a punchy result line.",
    "decode": "Decode: the tech word everyone's saying. `word`, `meaning` (plain, a bit witty), `try_this` (a concrete example), `number` (the Kamusi entry number).",
    "cap": "Cap or No Cap?: a claim young people hear online; verdict cap (false) | nocap (true) | kinda; `real` = the real talk.",
    "pov": "POV: Kesho: a near-future scenario written as a POV ('your AI agent ...'), `year`, `real` = what exists today. "
           "`cast`: 1-3 of {who, pose, mood, phone} from the stick cast (who can also be jua).",
    "build": "Build With Me: a real build (bots, automations, sites), shown as a flow of 3-6 steps, `stack` chips, `result` with a comment-to-get CTA.",
    "glasspoll": "Jua Asks (story): `hook`, a spicy-but-clean question, 2 options, `cta`.",
    "still": "Still in 2026?: `industry`, the outdated `thing` we still do (a habit or process, never a person), `old` way, `new` way that exists today, `cta`.",
    "spotlight": "Put Us On: a real African artist, creator or startup. `kind` (Artist/Creator/Startup), `name`, `country`, `what` they do, `why` it matters, `cta` (stream/follow/share). Positive only. MUST include a verifiable `source`.",
    "vichekesho": "Vichekesho: a 3-panel comic with the stick cast. Panels: [{bg, left?, right?}], bg one of jua|pwani|waridi|maziwa|ziwa. "
                  "Each side: {who: shosh|makanga|mama_mboga|boda|student|pro|farmer|jua, pose: stand|wave|point|think|cheer|walk|phone|shrug, "
                  "mood: happy|worried|wow|flat (cast also includes creator and techie), say?: speech max 80 chars, sms?: text on their phone max 90 chars}. "
                  "Max one speech + one SMS per panel, from different sides (or both from one character). Setup, turn, payoff. `punch` = the score line.",
}
EXPRESSIONS = ["happy", "wow", "wink", "thinking", "cool", "laugh", "visor"]


def _field_spec(template: str) -> dict:
    spec = {f: f"string, max {n} chars" for f, n in guard.SCHEMAS[template].items()}
    for f, (lo, hi, each) in guard.LISTS.get(template, {}).items():
        spec[f] = f"list of {lo}-{hi} strings, each max {each} chars"
    for f, allowed in guard.CHOICES.get(template, {}).items():
        spec[f] = f"one of {sorted(allowed)}"
    if template == "cover":
        spec["highlight"] = "integer index of the line to colour"
    if template == "kesho":
        spec.update({"n": "slide number", "total": "total slides"})
    if template in {"neno", "makanga", "ukweli", "tool", "usiibiwe", "cover"}:
        spec["expr"] = f"mascot expression, one of {EXPRESSIONS}"
    return spec


def learnings_text() -> str:
    """Top and bottom performers from past weeks (written by `pipeline.py learn`)."""
    f = HERE / "state" / "learnings.json"
    if not f.exists():
        return ""
    data = json.loads(f.read_text(encoding="utf-8"))
    top = "\n".join(f"- {x['series']} / {x['lane']}: score {x['score']} ({x['id']})" for x in data.get("top", []))
    low = "\n".join(f"- {x['series']} / {x['lane']}: score {x['score']} ({x['id']})" for x in data.get("bottom", []))
    return (f"\nWHAT WORKED LATELY (score = saves*3 + shares*4 + comments*2 + likes, per 1,000 reached)\n{top}"
            f"\nWHAT DIDN'T\n{low}\nLean into what worked; try a new angle on what didn't.\n")


def build_prompt(week_label: str, slots: list[dict], lanes: dict, examples: list[dict]) -> tuple[str, str]:
    lane_txt = "\n".join(f"- {k}: {v['who']}. Voice: {v['voice']}" for k, v in lanes.items())
    slot_txt = json.dumps([
        {"id": s["id"], "template": s["template"], "lane": s["lane"], "series_brief": SERIES[s["template"]],
         "fields": _field_spec(s["template"])}
        for s in slots
    ], ensure_ascii=False, indent=1)
    ex_txt = json.dumps(examples, ensure_ascii=False, indent=1)
    import trends
    system = BRAND_RULES + "\nAUDIENCE LANES\n" + lane_txt + learnings_text() + trends.prompt_block()
    user = f"""Write week {week_label}. Fill every slot below. Keep each post's `id` and `template` exactly.
Posts in the same carousel must tell one story in order. Don't repeat topics from the examples.

SLOTS
{slot_txt}

EXAMPLES OF FINISHED POSTS (style reference only)
{ex_txt}

Also write reach-everyone scripts from this week's content:
- "radio": a 2-minute community radio segment, host is Jua (about 250 words). Simple Kenyan English with a Kiswahili summary at the end.
- "voice_note": a 60-second WhatsApp voice-note script in relaxed Kenyan English.
- "sms": the week's Usiibiwe tip as one SMS, max 160 characters, no links.
- "reels": a 30-second voice-over for the Kesho Kutwa carousel.

Return ONLY JSON, no commentary:
{{"posts": [{{"id": "...", "template": "...", "lane": "...", "caption": "...", "source": "...(when needed)", "...fields": "..."}}],
 "scripts": {{"radio": "...", "voice_note": "...", "sms": "...", "reels": "..."}}}}"""
    return system, user


def model_id() -> str:
    return (os.environ.get("JUA_MODEL") or "").strip() or DEFAULT_MODEL


def call_claude(system: str, user: str, max_tokens: int = 12000) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (use --mock to test without it)")
    body = json.dumps({
        # `or`, not a default arg: GitHub passes an unset repo variable as an empty string
        "model": model_id(),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    workspace = (os.environ.get("ANTHROPIC_WORKSPACE_ID") or "").strip()
    if workspace:  # needed when the key belongs to the organisation rather than to one workspace
        headers["anthropic-workspace-id"] = workspace
    req = urllib.request.Request(API_URL, data=body, method="POST", headers=headers)
    # Retry only what is temporary: rate limits (429), server errors (5xx), overloaded (529), network drops
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504, 529) and attempt < 3:
                time.sleep(float(e.headers.get("retry-after") or 0) or 15 * 2 ** attempt)
                continue
            raise RuntimeError(f"Anthropic API {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 3:
                time.sleep(15 * 2 ** attempt)
                continue
            raise RuntimeError(f"Anthropic API unreachable: {e}") from e
    if data.get("stop_reason") == "max_tokens":
        raise RuntimeError("Anthropic API: reply was cut off at max_tokens (raise max_tokens)")
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


def extract_json(text: str) -> dict:
    """Parse the model's JSON even if it wrapped it in a code fence."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("model returned no JSON")
    return json.loads(m.group(0))


def _merge(slots: list[dict], drafted: list[dict]) -> list[dict]:
    """Model output fills content; the plan keeps control of id/template/bg/time/group."""
    by_id = {d.get("id"): d for d in drafted}
    out = []
    for s in slots:
        d = by_id.get(s["id"], {})
        locked = {k: s[k] for k in ("id", "template", "bg", "lane", "publish_at", "size", "group", "n", "total") if k in s}
        out.append({**d, **locked})
    return out


def mock_draft(slots: list[dict]) -> dict:
    """Offline stand-in for testing: reuses the launch posts for each template."""
    library = {}
    for p in json.loads((HERE / "content" / "posts.json").read_text(encoding="utf-8"))["posts"]:
        library.setdefault(p["template"], p)
    posts = []
    for s in slots:
        base = {k: v for k, v in library.get(s["template"], {}).items() if k not in {"id", "bg", "size"}}
        posts.append({**base, "id": s["id"]})
    return {"posts": posts, "scripts": {
        "radio": "Mock radio script.", "voice_note": "Mock voice note.",
        "sms": "Usiibiwe: Ukipata SMS ya 'pesa kimakosa', angalia salio lako la M-PESA kwanza. Usitume PIN.",
        "reels": "Mock reels voice-over."}}


CRITIC_BAR = 7.5
CRITIC_RUBRIC = """You are the toughest editor at a viral Kenyan content studio. Score each post 1-10 on:
- hook: would a 22-year-old in Nairobi stop scrolling within 2 seconds?
- send: is there an obvious person they'd DM this to? (sends drive reach)
- clarity: one idea, instantly understood, no jargon
- fresh: not generic advice they've seen 100 times; a real angle, a real Kenyan detail
- voice: sounds like a sharp Kenyan friend (Kenyan English), not a textbook or an ad
- craft: every word earns its place; the payoff lands
Be strict: 7 is good, 9 is exceptional, 10 is rare. Return ONLY JSON:
{"scores": [{"id": "...", "hook": n, "send": n, "clarity": n, "fresh": n, "voice": n, "craft": n,
             "note": "the single most important fix, in one sentence"}]}"""


def critique(posts: list[dict]) -> dict[str, dict]:
    """Scores posts against the masterpiece rubric. Returns {id: {..scores, avg, note}}."""
    payload = [{k: v for k, v in p.items() if k not in {"status", "guard", "publish_at", "bg", "seed"}} for p in posts]
    raw = extract_json(call_claude(CRITIC_RUBRIC, json.dumps(payload, ensure_ascii=False), max_tokens=4000))
    out = {}
    for s in raw.get("scores", []):
        keys = ("hook", "send", "clarity", "fresh", "voice", "craft")
        vals = [float(s.get(k, 0)) for k in keys]
        out[s.get("id")] = {**{k: s.get(k) for k in keys}, "avg": round(sum(vals) / len(vals), 1), "note": s.get("note", "")}
    return out


def elevate(week_label: str, slots: list[dict], lanes: dict, posts: list[dict]) -> list[dict]:
    """Critic pass: anything under the bar gets one rewrite with the critic's notes, then is re-scored."""
    scores = critique(posts)
    weak = [p for p in posts if scores.get(p["id"], {}).get("avg", 0) < CRITIC_BAR and p.get("status") != "needs_human"]
    if weak:
        system, _ = build_prompt(week_label, slots, lanes, [])
        notes = "\n".join(f"{p['id']} (avg {scores[p['id']]['avg']}): {scores[p['id']]['note']}" for p in weak)
        ask = ("An editor scored these posts below our bar. Rewrite each one to fix the note, keeping id, template "
               "and every required field. Make it genuinely better, not just different. Return JSON {\"posts\": [...]}.\n\n"
               + notes + "\n\nPosts:\n" + json.dumps(weak, ensure_ascii=False))
        rewritten = _merge([s for s in slots if s["id"] in {p["id"] for p in weak}],
                           extract_json(call_claude(system, ask)).get("posts", []))
        checked = {r.id: r for r in guard.check_all(rewritten)}
        better = {p["id"]: p for p in rewritten if checked[p["id"]].ok}
        if better:
            rescored = critique(list(better.values()))
            for pid, p in better.items():
                if rescored.get(pid, {}).get("avg", 0) > scores[pid]["avg"]:  # keep a rewrite only if it scores higher
                    p["status"], p["guard"] = "drafted", {"errors": [], "warnings": checked[pid].warnings}
                    posts = [p if q["id"] == pid else q for q in posts]
                    scores[pid] = rescored[pid]
    for p in posts:
        if p["id"] in scores:
            p["critic"] = scores[p["id"]]
    return posts


def draft_week(week_label: str, slots: list[dict], lanes: dict, mock: bool = False) -> tuple[list[dict], dict]:
    if mock:
        result = mock_draft(slots)
    else:
        examples = json.loads((HERE / "content" / "posts.json").read_text(encoding="utf-8"))["posts"][:4]
        system, user = build_prompt(week_label, slots, lanes, examples)
        result = extract_json(call_claude(system, user))

    posts = _merge(slots, result.get("posts", []))
    reports = guard.check_all(posts)
    failing = [r for r in reports if not r.ok]
    if failing and not mock:
        fix = "\n".join(f"{r.id}: {'; '.join(r.errors)}" for r in failing)
        system, _ = build_prompt(week_label, slots, lanes, [])
        repair_user = ("These posts failed checks. Return JSON {\"posts\": [...]} with ONLY the fixed posts, "
                       "same ids, all fields present:\n" + fix + "\n\nOriginal posts:\n" +
                       json.dumps([p for p in posts if p["id"] in {r.id for r in failing}], ensure_ascii=False))
        fixed = extract_json(call_claude(system, repair_user)).get("posts", [])
        fixed_by_id = {p.get("id"): p for p in _merge([s for s in slots if s["id"] in {r.id for r in failing}], fixed)}
        posts = [fixed_by_id.get(p["id"], p) for p in posts]
        reports = guard.check_all(posts)

    for p, r in zip(posts, reports):
        p["status"] = "drafted" if r.ok else "needs_human"
        p["guard"] = {"errors": r.errors, "warnings": r.warnings}
    if not mock:
        posts = elevate(week_label, slots, lanes, posts)
    return posts, result.get("scripts", {})
