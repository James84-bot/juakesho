"""
guard.py — every post passes this before it can be rendered or published.

Checks, per post:
  1. Schema: the template exists and every required field is present and not too long.
  2. Clean, grown-up content: workplace-safe language for young adults (no swearing, nothing sexual, no insults).
  3. Brand rules: no hype words, max 3 hashtags, no betting or get-rich-quick.
  4. Facts: posts that state numbers or history must carry a `source`.

Errors block the post. Warnings are shown to the human approver.

    python guard.py content/posts.json
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# field -> max characters. Keeps text inside the designed boxes.
SCHEMAS: dict[str, dict[str, int]] = {
    "intro":    {"hello": 30, "community": 90},
    "neno":     {"word": 14, "full": 34, "say": 20, "sw": 120, "en": 110, "note": 60, "example": 130},
    "makanga":  {"topic": 22, "like": 34, "explain": 130, "punch": 60},
    "ukweli":   {"claim": 60, "verdict_text": 18, "truth": 160},
    "tool":     {"title": 40, "warn": 50},
    "usiibiwe": {"title": 50, "sender": 24, "sms": 120},
    "shosh":    {"question": 70, "answer": 150, "punch": 60},
    "africa":   {"year": 4, "name": 16, "country": 16, "fact": 170, "now": 50},
    "hapa":     {"topic": 34, "hapa": 110, "huko": 110, "ask": 60},
    "cover":    {"series": 20, "kicker": 40},
    "kesho":    {"headline": 60, "leo": 100, "kesho": 100, "anza": 110},
    "poll":     {"question": 40, "cta": 30},
    "vichekesho": {"title": 30, "punch": 50},
    "hack":     {"hook": 40, "title": 60, "payoff": 50},
    "decode":   {"hook": 40, "word": 14, "meaning": 110, "try_this": 140},
    "cap":      {"claim": 70, "real": 120},
    "pov":      {"year": 4, "pov": 110, "real": 150},
    "build":    {"hook": 40, "title": 60, "result": 60},
    "glasspoll": {"hook": 30, "question": 40, "cta": 30},
    "still":    {"industry": 16, "thing": 70, "old": 90, "new": 100, "cta": 50},
    "spotlight": {"kind": 14, "name": 22, "country": 20, "what": 110, "why": 100, "cta": 50},
    "money":    {"hook": 40, "number": 14, "unit": 40, "what": 110, "why": 100, "check": 90},
    "straight": {"claim": 120, "who": 60, "truth": 70, "pride": 50, "claim_source": 240, "source": 240},
    "kumbuka":  {"date": 24, "event": 100, "status": 90, "ask": 50, "source": 240},
    "scorecard": {"who": 40, "office": 50, "verdict": 70, "source": 240},
    "sauti":    {"kicker": 24, "line": 120, "fact": 110, "source": 240},
    "kenya":    {"series": 20, "place": 40, "line": 110, "fact": 150, "source": 240},
    "promise":  {"who": 60, "promise": 120, "said": 50, "reality": 120, "ask": 60, "source": 240},
    "tazama":   {"headline": 70, "credit": 60, "rights": 120},
    "avatar":   {},
    "banner":   {"line": 40, "sub": 50},
}
LISTS: dict[str, dict[str, tuple[int, int, int]]] = {  # field -> (min items, max items, max chars each)
    "intro": {"promise": (2, 3, 50)},
    "tool": {"steps": (2, 4, 70)},
    "usiibiwe": {"tips": (2, 3, 70)},
    "cover": {"lines": (2, 4, 14)},
    "poll": {"options": (2, 2, 18)},
    "hack": {"moves": (2, 4, 70)},
    "build": {"flow": (3, 6, 45), "stack": (1, 5, 14)},
    "glasspoll": {"options": (2, 2, 22)},
    "straight": {"proof": (2, 3, 90)},
    "promise": {"proof": (1, 3, 90)},
    "kumbuka": {"facts": (1, 3, 90)},
}
CHOICES = {
    "ukweli": {"verdict": {"uongo", "ukweli", "kiasi"}},
    "cap": {"verdict": {"cap", "nocap", "kinda"}},
    "straight": {"verdict": {"false", "misleading", "missing_context"}},
    "promise": {"verdict": {"kept", "partly", "stalled", "broken", "ignored", "diverted"}},
    "kenya": {"series": {"Kenya at its best", "Built in Kenya"}},
}
FACT_TEMPLATES = {"kenya", "africa", "hapa", "usiibiwe", "kesho", "pov", "cap", "spotlight", "money", "straight", "promise", "sauti",
                  "kumbuka", "scorecard"}
# Feed templates where the picture must carry the message: the writer chooses a symbol (symbols.py)
SYMBOL_TEMPLATES = {"hack", "decode", "cap", "usiibiwe", "still", "glasspoll", "cover", "kesho", "spotlight",
                    "money", "build", "straight", "africa", "tool", "ukweli", "neno", "hapa", "shosh", "makanga", "poll"}
CIVIC_SERIES = {"money", "See Through It"}  # must carry a source
# Posts whose Reel should be told in beats (one punchy line at a time)
REEL_FIRST = {"sauti", "straight", "promise", "kumbuka", "scorecard", "money", "usiibiwe", "cap", "decode", "hack",
              "still", "africa", "spotlight", "makanga", "kenya"}
# Feed posts that should always carry a real photo (the design is photo-first)
PHOTO_FIRST = {"kenya", "kumbuka", "scorecard", "sauti", "hack", "decode", "cap", "money", "still", "straight", "promise", "africa", "spotlight", "usiibiwe", "cover"}
# Real, named people may appear with their licensed photo: celebrated (spotlight) or on the public record
PERSON_PHOTO_TEMPLATES = {"spotlight", "straight", "money", "cap", "promise", "sauti", "scorecard"}

# Clean-content list: English, Kiswahili and Sheng. Whole-word matches only.
# Kept deliberately mild here; extend blocklist.txt for your own additions.
BLOCK = {
    "damn", "hell", "crap", "stupid", "idiot", "shut up", "sexy", "nude", "drunk", "weed",
    "dumb", "useless people", "lazy africans", "backward people", "clowns", "trash people",
    "shenzi", "mjinga", "pumbavu", "mavi", "malaya", "fala", "bangi", "chang'aa",
}
# Topics the brand never touches (keeps it for everyone, everywhere)
BANNED_TOPICS = {
    # promoting gambling, never reporting on it (the betting tax and gambling debt are real political stories)
    "betting": r"\b(place (a|your) bets?|bet now|bet on (the )?(jackpot|match|game|team)|sure bets?|betting tips|best odds|odds (boost|of \d)|win the jackpot|"
               r"mega ?jackpot|(join|download|use) (sportpesa|betika|odibets|mozzartbet|shabiki)|cheza kamari)\b",
    "get-rich-quick": r"\b(get rich|guaranteed (profit|income|returns)|double your money|100% win)\b",
    # Criticising public office holders is in scope; telling people who to vote for is not
    "party-campaigning": r"\b((do not |don'?t )?vote (for|against) (him|her|them|uda|odm|jubilee|azimio|wiper|dcp|anc|kenya kwanza|"
                         r"the (opposition|government|ruling party))|vote (him|her|them) out|"
                         r"(odm|uda|jubilee|azimio|wiper|dcp|anc|kenya kwanza) (is|are) the (best|only|answer)|join (odm|uda|jubilee|azimio|wiper|dcp))\b",
    # The revolution is informed and peaceful: protest and voting yes, violence and harassment never
    "violence": r"\b((burn|torch|storm|attack|lynch|kill|beat|stone|loot) (the |their |his |her )?(parliament|state house|offices?|homes?|houses?|police|them|him|her|mps?|leaders?)|overthrow|coup|go to (his|her|their) (home|house)|find (his|her|their) (home|house|family)|doxx?)\b",
    "crypto-shill": r"\b(buy (now|this coin|this token)|to the moon|pump (and|n) dump|pump (it|this coin|this token)|"
                    r"100x|next big coin|guaranteed returns?)\b",   # 'pump' alone is a fuel pump
    # Banter wars roast a country's situations, never its people: no xenophobic slurs, no "go home" lines
    "xenophobia": r"\b(ma?kwerekwere|kwerekwere|amakwerekwere|go back (to|home)( to)? your (own )?country|"
                  r"(nigerians|south africans|ugandans|tanzanians|somalis|ethiopians|congolese) are (all )?(thieves|criminals|"
                  r"scammers|animals|lazy|stupid|dogs|monkeys|dirty)|(all|every) (nigerians?|south africans?|ugandans?|"
                  r"tanzanians?) (are|is) (a )?(scammers?|thieves?|criminals?)|yahoo boys? (all|every))\b",
}
ACRONYM_OK = {"MP", "MPS", "MCA", "MCAS", "IEBC", "KSH", "KES", "CS", "PS", "DCI", "IPOA", "KNCHR", "EACC", "ODM", "UDA",
              "DCP", "KRA", "NHIF", "SHA", "SHIF", "HELB", "CBD", "KPLC", "NTSA", "TSC", "KUCCPS", "CDF", "NG-CDF", "GDP",
              "US", "UK", "AU", "UN", "IMF", "AI", "ID", "OK", "TV", "FM", "M-PESA", "KOT", "GEN", "Z", "CEO", "IPO", "NYS",
              "LSK", "COTU", "KMPDU", "KNUT", "JSS", "CBC", "KCSE", "KCPE", "TIFA", "WHO", "EU", "USA", "SA", "DRC", "SGR"}


def _shouting(texts: list[str] | str) -> str:
    """'' if the copy is calm; otherwise what is too loud. Each piece (design text, caption) is judged on its own."""
    texts = [texts] if isinstance(texts, str) else texts
    text = " ".join(texts)
    found = []
    caps = sorted({w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", text) if len(w) >= 3 and w.isupper() and w.upper() not in ACRONYM_OK})
    if len(caps) >= 3:
        found.append("words in capitals (" + ", ".join(caps[:4]) + ")")
    if re.search(r"!{2,}|\?!|!\?", text) or any(t.count("!") > 2 for t in texts):
        found.append("too many exclamation marks")
    m = re.search(r"\b(breaking|urgent|shocking|you won'?t believe|must watch|share before|before it'?s deleted)\b", text, re.I)
    if m:
        found.append(f"'{m.group(0)}'")
    if len(re.findall("[\U0001F6A8\u203C\u2757\u26A0\U0001F525\U0001F4E2]", text)) > 1:
        found.append("alarm emojis")
    return "; ".join(found)


W5_TEMPLATES = {"sauti", "straight", "promise", "money", "scorecard", "kumbuka", "tazama"}

# Trending hashtags we never ride. We take no side: no tag for or against a politician or party, whoever's it is.
#   For: PR for any politician ("...Delivers", "ni tutam", "iko mbele", "imara": someone's campaign).
#   Against: campaigns to remove or reject a person ("...MustGo", "Wantam", "OneTerm"), and mocking nicknames.
#   Personal insults ("tapeli", "conman", "mwizi": name-calling, and the defamation risk sits with us).
# Issue tags (#FinanceBill2026, #HousingLevy, #EndAbductions) are fine: they name what people search, not a side.
PARTISAN_TAG = re.compile(r"delivers|tutam|ikombele|iko ?mbele|imara|tosha|forever|mustgo|must ?go|mustfall|wantam|"
                          r"one ?term|oneterm|kasongo|zakayo|riggy|wanjiku ?sacco|uda ?ni|odm ?ni|ruto ?out|raila ?out|"
                          r"gachagua ?out|tapeli|conman|mwizi|wezi|thief|thieves|liar|murderer|killer|traitor|msaliti", re.I)

SWAHILI_FILLERS = ["wueh", "aki", "bana", "mambo ni mengi", "hii nchi", "kwani ni kesho", "manze", "si ndio",
                   "very normal country", "we move"]
# Words and habits that make copy read machine-written. Kenyans scroll past anything that smells of AI.
NEVER_WORDS = {"leverage", "seamless", "game-changer", "game changer", "cutting-edge", "revolutionary", "delve",
               "passionate", "unlock", "tapestry", "testament to", "in today's", "it's not just", "navigate the",
               "landscape", "realm", "embark", "elevate", "harness", "foster", "pivotal", "crucial", "let's dive",
               "here's the thing", "buckle up", "in conclusion", "furthermore", "moreover", "empower", "robust",
               # brand-speak: we are wananchi, not a company
               "we're excited", "we are excited", "stay tuned", "don't miss", "let us know your thoughts",
               "check out our", "in this post", "dear followers", "kindly engage"}
# Tribe: we call out divisive politics (quote it, name who said it, source it), we never practise it.
TRIBE_TALK = r"\b(tribe|tribes|tribal|tribalism|kabila|ukabila)\b"
CALLOUT_TEMPLATES = {"straight", "sauti", "promise", "cap", "hack", "kumbuka", "scorecard"}
# Place names that share a word with a community (Lake Turkana, Turkana County, Samburu National Reserve, Embu town,
# Meru National Park) are places, not people: blanked out before the community check.
PLACE_FORMS = (r"\b(lake|mount|mt|county of)\s+(turkana|kenya|elgon|victoria|baringo|naivasha)\b|"
               r"\b(turkana|samburu|meru|embu|pokot|kisii|taita|kuria|teso)\s+(county|national|reserve|park|town|"
               r"university|level|referral|hospital|basin|wind|road|airport|stadium|market|hills?|south|north|west|east|central)\b")
COMMUNITIES = (r"\b(kikuyus?|luos?|kalenjins?|luhyas?|kambas?|kisiis?|merus?|mijikenda|somalis|turkanas?|embus?|kurias?|"
               r"taitas?|pokots?|tesos?|samburus?|gusii|agikuyu|abaluhya)\b")

_extra = Path(__file__).with_name("blocklist.txt")
if _extra.exists():
    BLOCK |= {w.strip().lower() for w in _extra.read_text(encoding="utf-8").splitlines() if w.strip()}


NICKNAMES = json.loads((Path(__file__).with_name("content") / "nicknames.json").read_text(encoding="utf-8"))["names"]
QUOTED = r"[\"“'‘]\s*{}\s*[\"”'’]"


def _check_nicknames(post: dict, rep: "Report") -> None:
    """Names Kenyans relate to, used fairly: real name alongside, mocking ones only quoted, slogans never ours."""
    everything = _all_text(post) + " " + str(post.get("caption", ""))
    for n in NICKNAMES:
        nick = n["nickname"]
        if not re.search(rf"(?<!\w){re.escape(nick)}(?!\w)", everything, re.I):
            continue
        if n["kind"] == "slogan":
            rest = everything.replace(str(post.get("claim", "")), "")
            if re.search(rf"(?<!\w){re.escape(nick)}(?!\w)", rest, re.I):
                rep.errors.append(f"'{nick}' is a campaign slogan: never in our voice (only inside a quoted claim we check)")
            continue
        if n["kind"] == "public-mocking":
            bare = re.sub(QUOTED.format(re.escape(nick)), "", everything, flags=re.I)
            if re.search(rf"(?<!\w){re.escape(nick)}(?!\w)", bare, re.I):
                rep.errors.append(f"'{nick}' is a mocking nickname: only as a quote of what Kenyans say "
                                  f"(e.g. Kenyans call him \"{nick}\"), never in our own voice")
        if n.get("match") and not re.search(rf"\b{re.escape(n['match'])}\b", everything, re.I):
            rep.errors.append(f"'{nick}' needs the real name in the same post: {n['name']} ({n['office']})")


@dataclass
class Report:
    id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _all_text(post: dict) -> str:
    parts = []
    for k, v in post.items():
        if k in {"id", "template", "bg", "size", "expr", "seed", "status", "source", "publish_at", "platforms", "trend", "lane", "guard"}:
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, dict):  # comic panels (what people say) and scorecard checks
                    for side in ("left", "right"):
                        c = x.get(side) or {}
                        parts.extend(str(c.get(k, "")) for k in ("say", "sms"))
                    parts.extend(str(x.get(k, "")) for k in ("test", "note"))
                else:
                    parts.append(str(x))
    return " ".join(parts)


SAFE_NAMES = {"Kenyans Are Asking", "Jua Kesho", "Bwana Ahadi", "Mama Mboga", "Google Translate", "National Assembly", "Mombasa Gate Bridge",
              "Controller Budget", "Auditor General", "Follow The Money", "See Through It"}


NOT_NAMES = {"The", "This", "That", "These", "Your", "Just", "Check", "Real", "Nobody", "Blocked", "Ksh", "See",
             "Through", "Why", "What", "How", "Read", "Save", "Send", "Kazi", "Tag", "Follow", "Money", "Every", "Some"}


FRAGMENT_START = re.compile(r"^\W*(meanwhile|yet|and|but|so|too bad|the catch|plot twist|imagine|guess what)\b", re.I)


def fragment(line: str) -> str:
    """Why a Reel beat reads as a fragment or a meme caption ('' when it is a proper sentence). Our readers are
    informed; half-sentences and trailing dots read as careless."""
    text = line.replace("*", "").strip()
    if "..." in text or "\u2026" in text:
        return "trails off with dots"
    if FRAGMENT_START.search(text):
        return f"opens with '{FRAGMENT_START.search(text).group(1)}' (a fragment that leans on the line before)"
    if len(text.split()) < 4:
        return "is under four words"
    if not re.search(r"[.?!:]['\"”’]?$|\d$|[A-Za-z]$", text):
        return "has no proper ending"
    if re.search(r"\?\s+\S", text):
        return "is a teaser question followed by its answer"
    return ""


def check(post: dict) -> Report:
    rep = Report(post.get("id", "?"))
    tpl = post.get("template")
    if tpl not in SCHEMAS:
        rep.errors.append(f"unknown template '{tpl}'")
        return rep
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", str(post.get("id", ""))):
        rep.errors.append("id must be lowercase letters, digits and dashes")

    for f, limit in SCHEMAS[tpl].items():
        v = post.get(f)
        if not isinstance(v, str) or not v.strip():
            rep.errors.append(f"missing field '{f}'")
        elif len(v) > limit:
            rep.errors.append(f"'{f}' is {len(v)} chars (max {limit})")
    for f, (lo, hi, each) in LISTS.get(tpl, {}).items():
        v = post.get(f)
        if not isinstance(v, list) or not (lo <= len(v) <= hi):
            rep.errors.append(f"'{f}' needs {lo}-{hi} items")
            continue
        for i, item in enumerate(v):
            if len(str(item)) > each:
                rep.errors.append(f"'{f}[{i}]' is {len(str(item))} chars (max {each})")
    for f, allowed in CHOICES.get(tpl, {}).items():
        if post.get(f) not in allowed:
            rep.errors.append(f"'{f}' must be one of {sorted(allowed)}")

    if tpl == "vichekesho":
        _check_comic(post, rep)
    sym = post.get("symbol")
    if sym:
        import symbols
        if sym not in symbols.SYMBOLS:
            rep.errors.append(f"unknown symbol '{sym}' (choose from symbols.py)")
    if len(str(post.get("message") or "")) > 120:
        rep.errors.append(f"'message' is {len(str(post.get('message')))} chars (max 120)")
    q = str(post.get("photo_query") or "")
    if q:
        if len(q) > 60:
            rep.errors.append(f"'photo_query' is {len(q)} chars (max 60)")
        critical = tpl in {"money", "straight", "spotlight"} or post.get("series") in CIVIC_SERIES
        if critical and re.search(r"\b(face|faces|portrait|selfie|man|woman|men|women|people|person|crowd|girl|boy)\b", q.lower()):
            rep.errors.append("photo_query on this post must show a scene, place or object, not people")
        if re.search(r"\b(logo|brand)\b", q.lower()):
            rep.errors.append("photo_query must not ask for logos or brands")
    if post.get("track") and not re.fullmatch(r"[\w .-]{3,80}\.(mp3|wav|m4a)", str(post["track"])):
        rep.errors.append("'track' must be a file name from content/music/tracks.json")
    pp = str(post.get("person_photo") or "")
    if pp:
        if tpl not in PERSON_PHOTO_TEMPLATES:
            rep.errors.append("real photos of people only on Put Us On, Set It Straight, Follow the Money and Cap or No Cap posts")
        if tpl != "spotlight" and not 4 <= len(str(post.get("person_role") or "").strip()) <= 60:
            rep.errors.append("a public figure's photo needs `person_role`: their public office (max 60 chars)")
        if tpl != "spotlight" and len(str(post.get("source") or "").strip()) < 8:
            rep.errors.append("a post naming a public office holder needs a `source` for every fact")
        if pp.startswith("people/"):
            if len(str(post.get("photo_rights") or "").strip()) < 8:
                rep.errors.append("person_photo needs `photo_rights`: who gave permission, or the press-kit link")
        elif not pp.startswith("commons:"):
            rep.errors.append("person_photo must be 'people/<file>' (with photo_rights) or 'commons:File:<name>'")
    if tpl == "straight":
        # Target the claim, never the person: say where it was said, quote it, answer with sourced facts.
        if len(str(post.get("claim_source", "")).strip()) < 8:
            rep.errors.append("Set It Straight needs `claim_source`: where exactly the claim was said")
        pass
    # Public conduct, never name-calling: we say what the record says, we don't call anyone names
    if re.search(r"\b(he|she|they|governor|senator|minister|cs|mp|mca|president|official)s? (is|are|was|were) (a |an )?"
                 r"(liar|liars|fool|fools|clown|clowns|idiot|idiots|fraud|frauds|thief|thieves|criminal|criminals|crook|crooks|corrupt)\b",
                 _all_text(post).lower()):
        rep.errors.append("criticise the conduct, not the person: say what the record shows (audit, ruling, charge), no name-calling")
    if re.search(r"\b(stole|looted|embezzled|thief|thieves|corrupt|kickback|bribe[ds]?)\b", _all_text(post).lower()):
        rep.warnings.append("serious allegation words: attribute them to the record ('the Auditor-General found', "
                            "'charged with', 'the court ruled') and keep the source in `source`")
    if tpl == "pov":
        cast = post.get("cast")
        if not isinstance(cast, list) or not 1 <= len(cast) <= 3:
            rep.errors.append("'cast' needs 1-3 characters")
        else:
            for c in cast:
                if not isinstance(c, dict) or c.get("who") not in COMIC_CAST:
                    rep.errors.append(f"pov cast: unknown character {c!r}")
                elif c.get("who") != "jua" and c.get("pose", "stand") not in COMIC_POSES:
                    rep.errors.append(f"pov cast: unknown pose '{c.get('pose')}'")

    text = _all_text(post)
    low = text.lower()
    _check_nicknames(post, rep)
    if tpl in PHOTO_FIRST and not (post.get("photo_query") or post.get("photo") or post.get("person_photo")):
        (rep.errors if tpl == "sauti" else rep.warnings).append("no photo: add a `photo_query` (a real Kenyan scene); visuals carry the post")
    if str(post.get("line", "")).count("*") % 2 or any(str(post.get(f, "")).count("*") % 2 for f in ("title", "thing", "truth", "claim", "headline", "question", "topic")):
        rep.errors.append("unbalanced *marker*: wrap the words to highlight in a pair of asterisks")
    # "vote for <Name>" is campaigning; "vote for six offices" is civic education
    m = re.search(r"\b[Vv]ote (for|against) (?!(?:the|your|a|an|all|every|each|whoever|who|six|five|leaders?|candidates?|offices?|"
                  r"positions?|people|someone|anyone)\b)([A-Z][a-z]+)", _all_text(post) + " " + str(post.get("caption", "")))
    if m:
        rep.errors.append(f"banned topic: party-campaigning ('vote {m.group(1)} {m.group(2)}'): we inform, we never tell people who to vote for")
    # our own polls are about issues and records, never candidate preference (see POLLS in draft.py)
    poll_text = " ".join([str(post.get("question", ""))] + [str(o) for o in post.get("options") or []])
    if tpl == "glasspoll" and re.search(r"\b(who|nani|which (candidate|leader|party))\b.{0,40}\b(vote|kura|win|shinda|president|rais|"
                                        r"2027|deserves?|should lead|best (leader|candidate))", poll_text, re.I):
        rep.errors.append("candidate-preference poll: we never run 'who will you vote for / who will win' polls; "
                          "ask about an issue or a leader's record, and report professional polls with their method")
    if "message" in post and not post.get("n") and tpl not in {"tazama", "cover"}:   # the weekly fairness count needs both
        for f in ("side", "tone"):
            if not post.get(f):
                rep.errors.append(f"no `{f}`: every post says {'side: government, opposition, both or none' if f == 'side' else 'tone: credit, criticism or explainer'}")
    if "message" in post and not post.get("n") and tpl in W5_TEMPLATES - {"kumbuka", "tazama"}:
        imp = str(post.get("impact") or "").strip()
        if not imp:
            rep.errors.append("no `impact`: say in one sentence what this changes for an ordinary Kenyan (pocket, services, rights, safety or vote)")
        elif len(imp) > 140:
            rep.errors.append(f"'impact' is {len(imp)} chars (max 140)")
        elif re.search(r"\b(affects (all|every)|all of us|everyone|every kenyan)\b", imp, re.I) and not re.search(r"\d", imp):
            rep.errors.append("'impact' is vague: name who is affected and how, with a number if the record has one")
    # a post written days before its slot can't say "today": it would be wrong the day it goes out
    if not post.get("hot") and tpl in {"sauti", "straight", "promise", "money", "scorecard", "glasspoll", "usiibiwe", "kumbuka"}:
        stamp = " ".join(str(post.get(k) or "") for k in ("message", "impact", "caption", "line", "headline", "fact",
                                                           "reality", "hook", "question", "title", "sub"))
        m = re.search(r"\b(today|tonight|yesterday|tomorrow|this (morning|afternoon|evening)|just now|hours ago)\b", stamp, re.I)
        if m:
            rep.errors.append(f"'{m.group(0)}': this post goes out days after it is written; use the date (e.g. 'on 14 Oct') instead")
    if len(str(post.get("event_query") or "")) > 60:
        rep.errors.append("'event_query' is over 60 characters: name the person and the occasion, 2-5 words")
    if post.get("side") is not None and post.get("side") not in {"government", "opposition", "both", "none"}:
        rep.errors.append("'side' must be government, opposition, both or none")
    if post.get("tone") is not None and post.get("tone") not in {"credit", "criticism", "explainer"}:
        rep.errors.append("'tone' must be credit, criticism or explainer")
    # who, where, when: every new civic post says who did it (office + name), where, and when (shown on the design)
    if "message" in post and not post.get("n") and tpl in W5_TEMPLATES:
        when = post.get("when") or (post.get("date") if tpl == "kumbuka" else None)
        for f, v, cap in (("who", post.get("who"), 60), ("where", post.get("where"), 24), ("when", when, 20)):
            if not str(v or "").strip():
                rep.errors.append(f"no `{f}`: say {dict(who='who did it (office and name)', where='where (county, town or national)', when='when (the date, or the deadline)')[f]}")
            elif len(str(v)) > cap:
                rep.errors.append(f"'{f}' is {len(str(v))} chars (max {cap})")
    # every new post tells Kenyans the one best thing to do (launch posts predate the rule: they carry no `message`)
    if "message" in post and not post.get("n") and tpl not in {"glasspoll", "cover", "tazama"}:
        act = str(post.get("action") or "").strip()
        if not act:
            rep.errors.append("no `action`: tell Kenyans the one best thing to do (where, how, by when)")
        elif len(act) > 90:
            rep.errors.append(f"'action' is {len(act)} chars (max 90)")
        elif re.fullmatch(r"(stay (informed|woke|alert)|be aware|share your thoughts|let us know)\.?", act, re.I):
            rep.errors.append("`action` is vague: give the concrete step (where, how, by when)")
    # no listicle numbering ("5 things", "3 reasons", "1/5"): it reads like a content farm
    m = re.search(r"\b(\d+|three|four|five|six|seven|ten) (things|reasons|ways|facts|signs|lessons|tips|truths)\b|(?<![\d.])\b\d/\d\b(?![\d.])",
                  text + " " + str(post.get("caption", "")), re.I)
    if m and tpl not in {"kesho", "cover"}:
        rep.errors.append(f"numbered listicle ('{m.group(0)}'): say the points, don't count them")
    # urgent, never shouty: capitals, stacked "!", BREAKING-style labels and alarm emojis read as clickbait
    loud = _shouting([text, str(post.get("caption", ""))])
    if loud:
        rep.errors.append(f"shouting reads as clickbait: {loud} (let the numbers carry the urgency)")
    # stock Swahili and slang fillers are the loudest "AI wrote this" tell: none of them, ever
    fillers = [f for f in SWAHILI_FILLERS if re.search(rf"(?<![\w]){re.escape(f)}(?![\w])", low)]
    if fillers:
        rep.errors.append(f"filler slang reads generated: {', '.join(fillers)} (say it in plain English)")
    if tpl == "tazama":   # someone else's clip: only with a recorded right to use it
        if post.get("rights_kind") not in {"permission", "own", "quote"}:
            rep.errors.append("clip without a recorded right to use it (permission / ours / short news quote)")
        if not 1 <= len(post.get("hook") or []) <= 2 or not 2 <= len(post.get("verdict") or []) <= 4:
            rep.errors.append("Tazama Hii needs 1-2 hook beats and 2-4 verdict beats")
        win = post.get("clip_window")
        cap = {"quote": 8.0}.get(post.get("rights_kind"), 40.0)
        if win and win[1] - win[0] > cap + 0.01:
            rep.errors.append(f"clip excerpt is {win[1] - win[0]:.1f}s (max {cap:.0f}s for this kind of clip)")
    if tpl == "scorecard":
        checks = post.get("checks")
        if not isinstance(checks, list) or not 3 <= len(checks) <= 5:
            rep.errors.append("'checks' needs 3-5 tests")
        else:
            for i, c in enumerate(checks):
                if not isinstance(c, dict) or c.get("result") not in {"pass", "fail", "unclear"}:
                    rep.errors.append(f"checks[{i}] needs result pass|fail|unclear")
                elif not 3 <= len(str(c.get("test", ""))) <= 40 or not 3 <= len(str(c.get("note", ""))) <= 80:
                    rep.errors.append(f"checks[{i}]: `test` max 40 chars and `note` max 80 chars, both required")
    if tpl == "kenya":
        q = str(post.get("photo_query") or "")
        if "kenya" not in q.lower():
            rep.errors.append("Kenya showcase: `photo_query` must name the place or project and include 'Kenya'")
        place_words = {w.lower() for w in re.findall(r"[A-Za-z']{4,}", str(post.get("place") or ""))}
        if place_words and not place_words & {w.lower() for w in re.findall(r"[A-Za-z']{4,}", q)}:
            rep.errors.append("Kenya showcase: `photo_query` must name the same place as `place`")
    beats = post.get("beats")
    if beats is not None:
        if not isinstance(beats, list) or not 3 <= len(beats) <= (6 if tpl == "tazama" else 5):
            rep.errors.append("'beats' (the Reel script) needs 3-5 sentences")
        else:
            for i, b in enumerate(beats):
                words = len(str(b).replace("*", "").split())
                if not isinstance(b, str) or len(b.replace("*", "")) > 72 or words > 12:
                    rep.errors.append(f"beats[{i}] is too long: max 12 words / 72 characters")
                elif str(b).count("*") % 2:
                    rep.errors.append(f"beats[{i}]: unbalanced *marker*")
                elif tpl != "tazama":
                    problem = fragment(str(b))
                    if problem:
                        rep.errors.append(f"beats[{i}] {problem}: write each beat as a complete, plain sentence")
    elif tpl in REEL_FIRST:
        rep.warnings.append("no `beats`: the Reel falls back to the animated card (write 3-6 punchy lines)")
    if tpl == "promise" and len(str(post.get("measure") or "")) > 16:
        rep.errors.append("'measure' is over 16 chars (e.g. '0 of 6', '12%')")
    for w in BLOCK:
        if re.search(rf"(?<![a-z']){re.escape(w)}(?![a-z'])", low):
            rep.errors.append(f"not clean for everyone: '{w}'")
    for topic, pattern in BANNED_TOPICS.items():
        if re.search(pattern, low):
            rep.errors.append(f"banned topic: {topic}")
    for w in NEVER_WORDS:
        if re.search(rf"(?<![a-z]){re.escape(w)}", low):
            rep.errors.append(f"sounds AI-written: '{w}' (say it the way a Kenyan would)")
    if "\u2014" in text or " \u2013 " in text:
        rep.errors.append("sounds AI-written: em dash; use a full stop or a comma")
    if re.search(TRIBE_TALK, low) and tpl not in CALLOUT_TEMPLATES:
        rep.errors.append("tribe only comes up when we call out divisive politics (Set It Straight, Sauti, Promise Tracker)")
    m = re.search(COMMUNITIES, re.sub(PLACE_FORMS, " ", low))
    if m:
        rep.errors.append(f"names a community ('{m.group(0)}'): describe divisive speech without repeating which "
                          "community was targeted; quote the speaker, never stereotype a people")

    caption = post.get("caption", "")
    if caption:
        tags = re.findall(r"#[A-Za-z]\w*", caption)
        bad = [t for t in tags if PARTISAN_TAG.search(t)]
        if bad:
            rep.errors.append(f"hashtag is a politician's PR or a personal insult ({', '.join(bad)}): never our tags")
        if len(tags) > 3:
            rep.errors.append(f"caption has {len(tags)} hashtags (max 3)")
        if len(caption) > 2000:
            rep.errors.append("caption over 2,000 characters")
    elif tpl not in {"avatar", "banner"}:
        rep.warnings.append("no caption yet")
    if caption and not re.search(r"\b(send|share|tag|save|comment|reply|vote|drop)\b", caption.lower()):
        rep.warnings.append("caption has no send/share/save call: sends and saves drive reach")

    # Civic content: systems and money, never accusations against a named person
    if tpl == "money" or post.get("series") in CIVIC_SERIES or any(c.get("who") == "ahadi" for p in post.get("panels", []) or [] for c in (p.get("left") or {}, p.get("right") or {})):
        if not post.get("source"):
            rep.errors.append("civic post needs a `source` (report, audit, study)")
        names = {m for m in re.findall(r"\b(?:[A-Z][a-z]{2,}\s){1,2}[A-Z][a-z]{2,}\b", text)
                 if m not in SAFE_NAMES and not set(m.split()) & NOT_NAMES}
        if names:
            rep.warnings.append(f"possible named person(s): {', '.join(sorted(names))}. Civic posts target systems, not people.")
    if tpl in FACT_TEMPLATES and not post.get("source"):
        rep.warnings.append("states facts but has no `source`; verify before approving")
    if re.search(r"\b(19|20)\d{2}\b|\d+%|\bksh\s?\d", low) and not post.get("source"):
        rep.warnings.append("contains a year, % or amount with no `source`")
    return rep


COMIC_CAST = {"shosh", "makanga", "mama_mboga", "boda", "student", "pro", "farmer", "creator", "techie", "ahadi", "jua"}
COMIC_POSES = {"stand", "wave", "point", "think", "cheer", "walk", "phone", "shrug", "sit"}
COMIC_BGS = {"jua", "pwani", "waridi", "maziwa", "ziwa"}  # light panels keep dark ink readable


def _check_comic(post: dict, rep: Report) -> None:
    panels = post.get("panels")
    if not isinstance(panels, list) or len(panels) != 3:
        rep.errors.append("'panels' needs exactly 3 panels")
        return
    for i, p in enumerate(panels, 1):
        if p.get("bg") not in COMIC_BGS:
            rep.errors.append(f"panel {i}: bg must be one of {sorted(COMIC_BGS)}")
        slots = []
        for side in ("left", "right"):
            c = p.get(side)
            if not c:
                continue
            if c.get("who") not in COMIC_CAST:
                rep.errors.append(f"panel {i} {side}: unknown character '{c.get('who')}'")
            if c.get("who") != "jua" and c.get("pose", "stand") not in COMIC_POSES:
                rep.errors.append(f"panel {i} {side}: unknown pose '{c.get('pose')}'")
            if c.get("say"):
                slots.append("a" if side == "left" else "b")
                if len(c["say"]) > 80:
                    rep.errors.append(f"panel {i} {side}: 'say' is {len(c['say'])} chars (max 80)")
            if c.get("sms"):
                slots.append("b" if side == "left" else "a")
                if len(c["sms"]) > 90:
                    rep.errors.append(f"panel {i} {side}: 'sms' is {len(c['sms'])} chars (max 90)")
        if len(slots) != len(set(slots)):
            rep.errors.append(f"panel {i}: two bubbles would overlap (one speech + one SMS max, from different sides)")
        if not p.get("left") and not p.get("right"):
            rep.errors.append(f"panel {i}: empty")
    if not rep.errors:  # geometry: measured with the real font, so a panel that can't fit fails here, not on render
        try:
            import render
            render.comic_layout(panels, 1080, 0)
        except ValueError as e:
            rep.errors.append(str(e))


def check_all(posts: list[dict]) -> list[Report]:
    reports = [check(p) for p in posts]
    ids = [p.get("id") for p in posts]
    for r in reports:
        if ids.count(r.id) > 1:
            r.errors.append("duplicate id")
    return reports


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "content" / "posts.json")
    posts = json.loads(path.read_text(encoding="utf-8"))["posts"]
    reports = check_all(posts)
    bad = 0
    for r in reports:
        mark = "✓" if r.ok else "✗"
        print(f"{mark} {r.id}")
        for e in r.errors:
            print(f"    ERROR   {e}")
        for w in r.warnings:
            print(f"    warning {w}")
        bad += not r.ok
    print(f"\n{len(reports) - bad}/{len(reports)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
