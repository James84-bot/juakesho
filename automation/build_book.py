"""
build_book.py — builds the Kenya on Record brand book as one self-contained HTML file.

Everything is read from the live system (brand.json palette, logo SVGs, rendered exports),
so the book always matches what the pipeline produces.

    python build_book.py            → brand-book/index.html (full page)
    python build_book.py --fragment → brand-book/artifact.html (body only, for publishing)
"""
from __future__ import annotations

import base64
import html
import io
import json
import sys
from pathlib import Path

from PIL import Image

import brandkit as bk
from palette import contrast

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXP = ROOT / "exports"
LOGO = ROOT / "assets" / "logo"
CAL = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))
POSTS = json.loads((HERE / "content" / "posts.json").read_text(encoding="utf-8"))["posts"]
B, P = bk.BRAND, bk.P
e = html.escape


def img_uri(path: Path, width: int, quality: int = 80) -> str:
    im = Image.open(path).convert("RGB")
    im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def svg_inline(path: Path, cls: str = "", label: str = "") -> str:
    s = path.read_text(encoding="utf-8")
    s = s.replace("<svg ", f'<svg class="{cls}" role="img" aria-label="{e(label)}" ', 1)
    return s.replace(' width="', ' data-w="').replace(' height="', ' data-h="')


FAMILIES = [
    ("ink", "Ink · flag black & white", "Backgrounds, text, rules: about 90% of every design. 950 is the default background, 50 is paper."),
    ("shuka", "Shuka · flag red", "The signature and the alarm: the sun in the logo, series tags, labels, the one highlight, FALSE, SCAM, BROKEN."),
    ("chai", "Chai · flag green", "Good news only: TRUE, KEPT, Africa's wins, the horizon in the logo. The Made in Africa background."),
]

SERIES = [
    ("Mon 07:30", "The People's Voice · Set It Straight", "sauti", "The week's biggest story in one plain sentence over a real photo, with the source and a clear demand."),
    ("Tue 12:45", "Kenya at its best", "kenya", "A real Kenyan place at its best: the photo or footage of the place itself and one sourced fact."),
    ("Wed 18:30", "Promise Tracker · The Chapter Six Test", "promise", "A leader's promise against the record, or a leader measured against the Constitution's integrity standard. Every side, same tests."),
    ("Thu 19:30", "Your Say", "glasspoll", "A poll on the week's biggest issue, posted as a Reel; people answer A or B in the comments."),
    ("Fri 17:00", "Same Standard", "straight", "The opposition held to the same test: their claims, their divisive talk, their own records."),
    ("Sat 11:00", "Built in Kenya", "kenya", "A finished, working public project, shown as it is today, with one sourced fact. Credit makes criticism believable."),
    ("Sun 18:00", "Your Say", "glasspoll", "A poll on the week's biggest issue. The answers pick next week's topics."),
    ("Daily", "The hot post · Watch This", "sauti", "Every morning the system ranks what Kenya is on, writes one post on the biggest story and sends it for approval in time for the evening. Clips you send become Watch This Reels."),
]

GLOSSARY = [
    ("Kenya on Record", "name", "What leaders promised and did, what our money paid for, and what Kenya has built: checked and kept on record."),
    ("Facts today. A better Kenya tomorrow.", "line", "Under the name on every profile."),
    ("Kenyans demand: …", "sign-off", "Every accountability post ends with one concrete demand to a named office, and the one thing to do."),
    ("Usiibiwe", "series", "“Don't get robbed.” Scam alerts, on the red background."),
    ("Promise Tracker", "series", "A leader's own promise against the record. Kept, partly kept, stalled or broken."),
    ("Set It Straight", "series", "Our answer to falsehoods and put-downs: the claim, quoted and sourced, then the facts."),
    ("Follow the Money", "series", "One public-money number, sourced, and how to check it yourself."),
    ("Watch This", "series", "A real clip someone filmed, credited, with our take around it."),
    ("We Remember", "series", "Documented events, on their anniversaries."),
    ("Your Say", "series", "The Sunday poll on the week's biggest issue."),
    ("Credit Where Due", "series", "Applause for what was genuinely delivered, with proof, whoever delivered it."),
    ("Same Standard", "rule", "Government and opposition get the same test. Ridicule the decision and the record, never the person."),
    ("Kenyan English", "voice", "Plain Kenyan English. Kiswahili only where a Kenyan would really say it, never as decoration. No numbering, no shouting."),
]

MONEY = [
    ("Facebook monetisation", "Original Reels", "Our own Reels and permitted clips qualify; reposts never do."),
    ("YouTube Partner Program", "Shorts and long video", "The same Reels as Shorts, and longer explainers."),
    ("Labelled brand deals", "Partners", "Brands young Kenyans use. Always labelled. Never betting, alcohol, predatory loans or political parties."),
    ("Commissioned series", "Partners", "NGOs and civic programmes pay for explainer series, clearly credited, editorially independent."),
    ("Autopilot builds", "Services", "The same content engine, set up for other brands. Each build funds more free content."),
]

DAY_90 = [
    ("Weeks 1–2", "Claim the Kenya on Record name everywhere. Profiles from the kit, the WhatsApp Channel and the Telegram bot. First posts."),
    ("Weeks 3–6", "Autopilot on: daily posts, about 15 minutes of approvals. Let the Sunday poll choose topics."),
    ("Weeks 7–10", "Reels every day; Tazama Hii clips from followers. Keep what earns shares and saves, drop the rest."),
    ("Weeks 11–13", "Apply for Facebook monetisation and the YouTube Partner Program. Build the sponsor deck from real reach."),
]

FLOW = [
    ("Sun 17:00", "Plan", "calendar.json picks each day's series, audience lane and background."),
    ("", "Draft", "The AI writer (free Gemini key, or Claude with a weekly cap) writes the week in our voice, with a photo search for each post."),
    ("", "Guard", "Clean, grown-up, sourced, no name-calling, no campaigning. Failures go back for repair."),
    ("", "Critic", "A tough-editor pass scores every post; weak ones are rewritten."),
    ("", "Design", "Real photo, headline fitted with the real font, then visual QA on every pixel of text."),
    ("You · 15 min", "Approve", "Each design arrives on Telegram with ✅ / ❌. Nothing posts without your tap."),
    ("Every 2 h", "Publish", "Approved posts go live on Instagram and Facebook at their time."),
]


def ramp_html(key: str, name: str, use: str) -> str:
    cells = []
    for step, hex_ in P[key].items():
        on = P["ink"]["950"] if contrast(hex_, P["ink"]["950"]) >= contrast(hex_, "#FFFFFF") else "#FFFFFF"
        brand = ' class="is-brand"' if hex_ == B["colors"].get({"ink": "usiku", "shuka": "shuka", "chai": "chai"}[key], {}).get("hex") else ""
        cells.append(f'<li{brand} style="--c:{hex_};--t:{on}"><b>{step}</b><code>{hex_}</code></li>')
    return (f'<div class="ramp"><div class="ramp-head"><h3>{e(name)}</h3><p>{e(use)}</p></div>'
            f'<ol class="shades">{"".join(cells)}</ol></div>')


def pair(fg: str, bg: str, label: str) -> str:
    r = contrast(fg, bg)
    return (f'<li style="--f:{fg};--b:{bg}"><span class="pair-demo">Aa</span><span><b>{e(label)}</b>'
            f'<small>{r:.1f}:1 · {"AAA" if r >= 7 else "AA" if r >= 4.5 else "AA large"}</small></span></li>')


def build_body() -> str:
    lock_light = svg_inline(LOGO / "wordmark-on-light.svg", "logo logo--light", "Kenya on Record")
    lock_dark = svg_inline(LOGO / "wordmark-on-dark.svg", "logo logo--dark", "Kenya on Record")
    ink, shuka, chai = P["ink"], P["shuka"], P["chai"]
    ramps = "".join(ramp_html(*f) for f in FAMILIES)
    pairs = "".join([
        pair(ink["50"], ink["950"], "Paper on night (text)"),
        pair(ink["300"], ink["950"], "Ink 300 on night (body)"),
        pair(shuka["400"], ink["950"], "Red on night (labels, numbers)"),
        pair("#FFFFFF", shuka["600"], "White on red (tags, verdicts, alerts)"),
        pair("#FFFFFF", chai["700"], "White on green (kept, true, Africa)"),
        pair(ink["900"], ink["50"], "Ink on paper"),
        pair(shuka["600"], ink["50"], "Red on paper (labels)"),
        pair(chai["300"], ink["950"], "Green on night (proof numbers)"),
    ])

    def thumb(pid: str | None, tpl: str, w: int = 220) -> str:
        post = next((p for p in POSTS if (pid and p["id"] == pid) or (not pid and p["template"] == tpl)), None)
        if not post or not (EXP / "posts" / (post["id"] + ".png")).exists():   # not rendered yet: no thumbnail
            return ""
        h = 391 if post.get("size") == "story" else 275
        return f'<img src="{img_uri(EXP / "posts" / (post["id"] + ".png"), w)}" alt="{e(tpl)} example" width="{w // 2}" height="{h // 2 if w == 220 else h}">'

    series_rows = "".join(
        f'<li class="series-row"><span class="when">{when}</span><div><h3>{e(name)}</h3><p>{e(what)}</p></div>{thumb(None, tpl)}</li>'
        for when, name, tpl, what in SERIES)
    lanes = "".join(f'<li><b>{e(k)}</b><span>{e(v["who"])}</span></li>' for k, v in CAL["lanes"].items())
    gallery = "".join(
        f'<figure class="g-item"><img src="{img_uri(EXP / "posts" / (p["id"] + ".png"), 400)}" alt="{e(p["id"])}" '
        f'width="400" height="{711 if p.get("size") == "story" else 500}" loading="lazy"><figcaption>{e(p["id"])}</figcaption></figure>'
        for p in POSTS if (EXP / "posts" / (p["id"] + ".png")).exists())   # an example not rendered yet is left out
    prof = EXP / "profiles"
    profiles = (f'<figure class="pf pf--wide"><img src="{img_uri(prof / "youtube-banner-2560x1440.png", 900)}" alt="YouTube banner" width="900" height="506"><figcaption>YouTube 2560×1440, key content in the safe zone</figcaption></figure>'
                f'<figure class="pf"><img src="{img_uri(prof / "x-header-1500x500.png", 700)}" alt="X header" width="700" height="233"><figcaption>X header 1500×500</figcaption></figure>'
                f'<figure class="pf"><img src="{img_uri(prof / "facebook-cover-1640x624.png", 700)}" alt="Facebook cover" width="700" height="266"><figcaption>Facebook cover 1640×624</figcaption></figure>'
                f'<figure class="pf pf--av"><img src="{img_uri(prof / "avatar-night.png", 300)}" alt="Profile picture, night" width="140" height="140"><img src="{img_uri(prof / "avatar-red.png", 300)}" alt="Profile picture, red" width="140" height="140"><figcaption>Profile pictures: survive the circle crop</figcaption></figure>')
    glossary = "".join(f'<div class="gl"><dt>{e(w)}<small>{e(k)}</small></dt><dd>{e(d)}</dd></div>' for w, k, d in GLOSSARY)
    money = "".join(f'<li><span class="m-tag">{e(t)}</span><h3>{e(n)}</h3><p>{e(d)}</p></li>' for n, t, d in MONEY)
    plan90 = "".join(f'<li><span class="when">{w}</span><p>{e(d)}</p></li>' for w, d in DAY_90)
    flow = "".join(f'<li><span class="f-when">{e(w)}</span><b>{e(n)}</b><span>{e(d)}</span></li>' for w, n, d in FLOW)
    reel_strip = ""
    for pid in ("01-hack-lecture-notes", "14-money-idle-funds", "18-straight-africa-country", "17-cant-wait"):
        cover = EXP / "reels" / f"{pid}-cover.jpg"
        if cover.exists():
            reel_strip += f'<figure class="reel"><img src="{img_uri(cover, 300)}" alt="Reel: {pid}" width="150" height="267"><figcaption>{pid}.mp4</figcaption></figure>'
    kinds = {"self": "Their own nickname: fine in our voice.", "neutral": "Factual or affectionate: fine in our voice.",
             "public-mocking": "Only as a quote of what Kenyans say, then the facts.", "slogan": "Never in our voice; only inside a claim we check."}
    nick_cards = "".join(f'<li><b>{e(n["nickname"])}</b><span>{e(n.get("name", "Campaign slogan"))}'
                         f'{" · " + e(n["office"]) if n.get("office") else ""}. {e(kinds[n["kind"]])}</span></li>'
                         for n in json.loads((HERE / "content" / "nicknames.json").read_text(encoding="utf-8"))["names"])
    examples = "".join(f'<figure class="ex">{thumb(pid, "", 520)}</figure>' for pid in ("00b-sauti-payslip", "01b-civic-six-votes", "18-straight-africa-country"))

    return f"""
<header class="topbar">
  <nav class="toc" aria-label="Sections">
    <a href="#idea">Idea</a><a href="#logo">Logo</a><a href="#colour">Colour</a><a href="#type">Type</a><a href="#layout">Layout</a>
    <a href="#photos">Photos</a><a href="#week">The week</a><a href="#voice">Voice</a><a href="#speak">Speaking up</a>
    <a href="#office">Office holders</a><a href="#motion">Motion</a><a href="#quality">Quality</a><a href="#launch">Launch set</a>
    <a href="#autopilot">Autopilot</a><a href="#money">Money</a>
  </nav>
</header>

<main class="book">
  <section class="hero" aria-labelledby="t-hero">
    <h1 id="t-hero">{lock_light}{lock_dark}<span class="sr">Kenya on Record</span></h1>
    <p class="tagline">{e(B['tagline_sw'])} <span>{e(B['tagline_en'])}</span></p>
    <p class="lede">An independent Kenyan channel for 18–30s: what leaders promised and did, what our money paid for, and what Kenya has built, all with sources. Fair to every side, clear, and clean.</p>
  </section>

  <section class="manifesto" aria-label="Manifesto">
    <p class="kicker">Manifesto</p>
    <p class="man-line">Africa can't wait.</p>
    <p class="man-sub">Know how your country works. Check every claim. Follow the money. Register, vote, show up for public participation, and hold every leader to their word. Peacefully, legally, loudly.</p>
  </section>

  <section id="idea" class="sec" aria-labelledby="t-idea">
    <p class="kicker">01</p><h2 id="t-idea">The idea</h2>
    <p class="big">Informed Kenyans holding the people in power to account with proof, and showing what Kenya gets right. A real photo, one plain headline, the facts, and a clear demand to the office responsible. Not with any government or party: every side, same standard.</p>
    <ul class="pillars">
      <li><b>Demand</b><span>One concrete demand per accountability post, to a named office, with the one thing to do.</span></li>
      <li><b>Prove</b><span>Every number and claim carries a source. Accuracy is what makes us fearless.</span></li>
      <li><b>Belong</b><span>Every Kenyan welcome, whatever their party, tribe or county.</span></li>
      <li><b>Proud</b><span>Kenya at its best and what Kenya builds, shown with the same care as what goes wrong.</span></li>
    </ul>
  </section>

  <section id="logo" class="sec" aria-labelledby="t-logo">
    <p class="kicker">02</p><h2 id="t-logo">Logo</h2>
    <p class="note">The mark is a record: a sheet with a folded corner in the flag&rsquo;s black, with a tick for what has been checked, and the flag&rsquo;s red and green bands, with their white edges, across it. National colours only, so no party colour leads. The wordmark is KENYA ON RECORD in Inter Tight Black. All files are outlined SVGs in <code>assets/logo/</code>.</p>
    <div class="logos">
      <div class="lg lg--night">{svg_inline(LOGO / 'wordmark-on-dark.svg', 'lg-svg', 'Wordmark on night')}</div>
      <div class="lg lg--paper">{svg_inline(LOGO / 'wordmark-on-light.svg', 'lg-svg', 'Wordmark on paper')}</div>
      <div class="lg lg--red">{svg_inline(LOGO / 'wordmark-mono-light.svg', 'lg-svg', 'One-colour wordmark on red')}</div>
      <div class="lg lg--icons">{svg_inline(LOGO / 'icon-night.svg', 'lg-ic', 'Icon, night')}{svg_inline(LOGO / 'icon-red.svg', 'lg-ic', 'Icon, red')}{svg_inline(LOGO / 'stacked-on-dark.svg', 'lg-stack', 'Stacked logo')}</div>
    </div>
    <ul class="rules">
      <li>Clear space: the height of the sun on every side.</li>
      <li>Minimum width 120&nbsp;px for the wordmark; below that, use the icon.</li>
      <li>On red or green, use the one-colour white version (the sun would disappear). Never recolour, outline, shadow or stretch it.</li>
      <li>Flag colours, never the flag itself or the coat of arms: national symbols are protected by law; their colours are free to use.</li>
    </ul>
  </section>

  <section id="colour" class="sec" aria-labelledby="t-colour">
    <p class="kicker">03</p><h2 id="t-colour">Colour</h2>
    <p class="note">The colours of the Kenyan flag: black, white, red, green. They belong to every Kenyan and to no party (in Kenyan politics yellow reads as UDA and orange as ODM, so we use neither). Three families, eleven shades each, built in OKLCH so every step looks evenly spaced. Outlined swatches are the brand values. Ink does the work; red signs it and sounds the alarm; green only ever means good news. Regenerate with <code>python palette.py</code>.</p>
    <div class="ramps">{ramps}</div>
    <h3 class="sub">Approved pairs</h3>
    <ul class="pairs">{pairs}</ul>
    <ul class="rules">
      <li>One red highlight per design. If everything is red, nothing is.</li>
      <li>Red: the brand, and false, scam, broken. Green: true, kept, a win. Never use green as decoration.</li>
      <li>Backgrounds: night (default), red (scam alerts, launch moments), green (Made in Africa), paper (explainers).</li>
    </ul>
  </section>

  <section id="type" class="sec" aria-labelledby="t-type">
    <p class="kicker">04</p><h2 id="t-type">Type</h2>
    <div class="types">
      <div class="ty"><span class="lbl">Inter Tight · ExtraBold 800 · −2.5% tracking</span><p class="ty-d">Sh304bn sitting idle in 14 projects</p><small>Headlines and numbers. Sized by measuring the real font file, so a headline never spills out of its box.</small></div>
      <div class="ty"><span class="lbl">Inter Tight · ExtraBold 800 · uppercase · +10% tracking</span><p class="ty-l">Why you should care</p><small>Labels and series tags. Short, in red.</small></div>
      <div class="ty"><span class="lbl">Inter · Medium 500 / SemiBold 600</span><p class="ty-b">59% of the Sh515bn set aside for 14 flagship projects over five years was never used, says the Auditor-General.</p><small>Body text, steps, facts. Never below 26&nbsp;px on a 1080&nbsp;px post.</small></div>
    </div>
  </section>

  <section id="layout" class="sec" aria-labelledby="t-layout">
    <p class="kicker">05</p><h2 id="t-layout">Layout</h2>
    <p class="note">One grid for everything, the way news channels do it. 72&nbsp;px margins. Top bar: series tag left, context right. Then label, headline, the facts as ruled rows, and a footer rule with the logo. No shapes, stickers, mascots or handwriting: the photo and the type carry it.</p>
    <div class="examples">{examples}</div>
    <ul class="rules">
      <li>Headline first, always plain words: a stranger knows the topic in two seconds.</li>
      <li>Lists are numbered rows (01, 02, 03) between thin rules. Verdicts are flat solid labels: FALSE, CAP, SCAM.</li>
      <li>If text grows, the layout shrinks the headline first, then the body, and checks it again. Nothing ever runs into the footer.</li>
    </ul>
  </section>

  <section id="photos" class="sec" aria-labelledby="t-photos">
    <p class="kicker">06</p><h2 id="t-photos">Photos &amp; people</h2>
    <ul class="cards">
      <li><b>Photo-first</b><span>Every feed post asks for a real photo of a Kenyan scene that <em>is</em> the feeling: the queue, the payslip, the stalled site. Sauti posts fill the whole frame with it. The checker flags any post without one.</span></li>
      <li><b>Free and licensed</b><span>Real Kenyan scenes from Wikimedia Commons (free, no key, only CC0 / public domain / CC&nbsp;BY), Pexels (free key) or your own shots. Credited on the image and in the caption.</span></li>
      <li><b>Real people, real photos</b><span>People we celebrate, and public office holders on the record, appear in their real photo: their permission, a press kit, or a CC0 / public-domain / CC&nbsp;BY Wikimedia Commons photo (checked automatically, credited).</span></li>
      <li><b>Honest labels</b><span>On civic posts a stock scene is marked &ldquo;Illustrative photo&rdquo;. A stranger's face never stands in for someone we name.</span></li>
      <li><b>Never</b><span>Edited or mocking photos of real people, AI faces, deepfakes, logos, photos we have no right to use.</span></li>
    </ul>
  </section>

  <section id="week" class="sec" aria-labelledby="t-week">
    <p class="kicker">07</p><h2 id="t-week">The week</h2>
    <p class="note">Every series owns a day and a time. When a series owns a day, people start waiting for it.</p>
    <ul class="series">{series_rows}</ul>
    <h3 class="sub">Who it's for</h3>
    <ul class="lanes">{lanes}</ul>
  </section>

  <section id="voice" class="sec" aria-labelledby="t-voice">
    <p class="kicker">08</p><h2 id="t-voice">Voice: plain, informed, fair</h2>
    <p class="big">Our readers follow the news. We write like a sharp Kenyan news editor: simple words in complete, correct sentences, the facts they don&rsquo;t already have, and one clear demand. No slang, no sarcasm, no meme phrases.</p>
    <ol class="cards cards--num">
      <li><b>The news</b><span>The whole story in one sentence: who did what, with the number.</span></li>
      <li><b>The proof</b><span>One hard, sourced fact: the report, the page, the date, the link.</span></li>
      <li><b>What it means</b><span>Who pays or what changes for ordinary Kenyans, with the number.</span></li>
      <li><b>The demand</b><span>&ldquo;Kenyans demand: the Treasury publishes the full list of lenders.&rdquo; Lawful, possible, to a named office.</span></li>
    </ol>
    <p class="note" style="margin-top:22px">We say &ldquo;we&rdquo; and &ldquo;our money&rdquo;, never &ldquo;you should&rdquo;. Plain English throughout; a Kiswahili word only where every Kenyan would say it that way.</p>
    <div class="doit">
      <div class="yes"><span class="lbl">Say it like this</span><p>&ldquo;Fake job offers on WhatsApp: real jobs never ask you to pay to start.&rdquo; Plain topic words, a fact, something to do.</p></div>
      <div class="no"><span class="lbl">Never like this</span><p>&ldquo;People from [place] are the ones who steal.&rdquo; No blaming groups, no talking down, no vague teaser headlines.</p></div>
    </div>
    <ul class="cards cards--3">
      <li><b>Attract</b><span>First words and the photo open a question, a surprise or instant recognition. Specific beats general.</span></li>
      <li><b>Sustain</b><span>Each line pays off the last and opens the next. The most surprising fact goes second.</span></li>
      <li><b>Reward</b><span>Something to use, say or send within the hour. That's why they come back.</span></li>
      <li><b>Calm</b><span>The facts carry the weight. No jokes on civic posts, no exclamation marks.</span></li>
      <li><b>Pride</b><span>Show Kenya&rsquo;s places and finished projects with names, places and years.</span></li>
      <li><b>Punch up</b><span>Systems, tactics, decisions of the powerful. Never down at victims, ordinary people or groups.</span></li>
    </ul>
    <h3 class="sub">Sound natural</h3>
    <p class="note">Informed ordinary Kenyans, not a media house and not a meme page. Complete sentences, natural English that any Kenyan of any age reads easily. No slang or internet shorthand.</p>
    <h3 class="sub">Never sound machine-made</h3>
    <p class="note">No em dashes, no &ldquo;it&rsquo;s not just X, it&rsquo;s Y&rdquo;, no &ldquo;delve&rdquo;, &ldquo;navigate&rdquo;, &ldquo;unlock&rdquo;. The checker blocks these before anything is sent for approval.</p>
    <dl class="glossary">{glossary}</dl>
  </section>

  <section id="speak" class="sec sec--night" aria-labelledby="t-speak">
    <p class="kicker">09</p><h2 id="t-speak">Speaking up</h2>
    <p class="note">We are Africans; Africa's story is ours to tell. For every critical post we publish at least two that celebrate or teach.</p>
    <ul class="cards">
      <li><b>Promise Tracker</b><span>A leader's own words, quoted with where and when, against the official record. Kept, partly, stalled or broken: every side judged the same way.</span></li>
      <li><b>Set It Straight</b><span>A falsehood, a politician's claim or a put-down of Kenya and Africa: quote it exactly, say who said it and where, stamp the verdict, then the facts with 2–3 sourced proofs.</span></li>
      <li><b>Follow the Money</b><span>One public number from the Auditor-General, the Controller of Budget or reputable media, and how to check it yourself.</span></li>
      <li><b>See Through It</b><span>Bought trends, paid crowds, exploited faith: we show the tactic so people can spot it. Faith itself is never attacked.</span></li>
      <li><b>Proudly African</b><span>Artists, startups, inventions, athletes, farmers. Pride, never propaganda: real wins are convincing enough.</span></li>
      <li><b>The revolution is informed</b><span>Register, vote, attend public participation, read the report, ask your MP, share the facts. Peaceful and legal, always: the checker blocks calls to violence and harassment.</span></li>
      <li><b>Never</b><span>Tribe, in any direction. Private individuals. Insults. Telling anyone who to vote for. Anything we can't prove.</span></li>
    </ul>
  </section>

  <section id="office" class="sec" aria-labelledby="t-office">
    <p class="kicker">10</p><h2 id="t-office">Public office holders</h2>
    <p class="note">Kenyans have the right to criticise the people they pay. We do it without fear and without error: the facts do the punching.</p>
    <div class="doit">
      <div class="yes"><span class="lbl">Fair game</span><p>Decisions, spending, promises vs delivery, public statements, votes, attendance, audit findings, court rulings. Named, with their official or licensed photo and their office, every fact sourced. Every side held to the same standard.</p></div>
      <div class="no"><span class="lbl">Never</span><p>Family, health, looks, tribe, faith, private life. Calling anyone a thief or corrupt ourselves: we say what the record says (&ldquo;the Auditor-General found&rdquo;, &ldquo;charged with&rdquo;, &ldquo;the court ruled&rdquo;). Edited or mocking photos. Calls to harass anyone.</p></div>
    </div>
    <h3 class="sub">The goal for 2027</h3>
    <p class="note">Not just a change of faces: leadership in the right hands. Kenya has rarely held leaders accountable, so we do it every week, and measure every leader and serious candidate, from every side, against the Constitution's own standard (Chapter Six, Articles 73&ndash;80: Leadership and Integrity) and their record. We never endorse; we hand voters the records. That is why our verdicts will be trusted.</p>
    <h3 class="sub">Call it out</h3>
    <ul class="cards">
      <li><b>Leaders who take advantage</b><span>Money that vanished, projects launched and abandoned, promises broken. Named, with their own words and the record.</span></li>
      <li><b>Divisive politics</b><span>Quote the exact words, name the speaker, give the clip and the date, and say plainly why it divides us. Never repeat a slur or name the community targeted.</span></li>
      <li><b>No favourites</b><span>Government and opposition, old names and new: one standard. That is what makes us untouchable.</span></li>
      <li><b>Hatutasahau</b><span>Protest killings, abductions, hired goons, deaths in custody: documented by KNCHR, IPOA, the courts or reputable media, date by date, with what accountability has followed. Anniversaries come up automatically.</span></li>
      <li><b>Church and state</b><span>Cash at the pulpit, clergy campaigning, public favours to religious bodies. We scrutinise the relationship, never faith or believers.</span></li>
      <li><b>Keep the record</b><span>Every published post is logged with its exact text and sources in <code>state/evidence.jsonl</code>: the defence file if anyone takes us to court.</span></li>
    </ul>
    <h3 class="sub">Names people relate to</h3>
    <p class="note">Kenyans already have names for their leaders, and those names stop the scroll. We use them by the rules in <code>content/nicknames.json</code>, which the writer reads and the checker enforces. The real name and office are always in the same post.</p>
    <ul class="cards">{nick_cards}</ul>
    <p class="note small" style="margin-top:18px">Why the care: Article 33 of the Constitution protects expression, and the High Court struck down criminal defamation in 2017. Civil defamation and the Computer Misuse and Cybercrimes Act still punish <em>false</em> statements of fact, and photographers own their photos. The checker blocks name-calling and campaigning, flags allegation words, and requires a source and a licensed photo. This is guidance, not legal advice: for a high-stakes post, ask a media lawyer first.
    Sources: <a href="https://www.amnestykenya.org/guard-your-right-to-criticise-and-hold-all-state-officers-accountable/">Amnesty Kenya</a> · <a href="https://globalfreedomofexpression.columbia.edu/wp-content/uploads/2017/02/Petition_397_of_2016.pdf">Okuta v Attorney General (2017)</a> · <a href="https://tikenya.org/wp-content/uploads/2023/05/A-Review-of-the-State-of-Whistleblower-Protection-and-Defamation-Laws-in-Kenya_TI-Kenya.pdf">TI-Kenya on defamation law</a> · <a href="https://ggalaw.co.ke/2020/04/05/the-law-on-reputation/">GGA Law on reputation</a></p>
  </section>

  <section id="motion" class="sec" aria-labelledby="t-motion">
    <p class="kicker">11</p><h2 id="t-motion">Motion &amp; sound</h2>
    <p class="note">Every post ships as a 9:16 Reel told in <b>beats</b>: 3&ndash;5 complete sentences, one at a time, over the real photo or real footage. The first line is the whole news and is on screen from the first frame; then the proof, what it means, and the demand. The hardest word lands on the red marker; a bar counts down each line.</p>
    <div class="reels">{reel_strip}</div>
    <ul class="cards">
      <li><b>Trending sounds</b><span>The strongest reach. Tap &ldquo;🎵 I'll post it&rdquo; on Telegram, then add a trending Kenyan sound in the app (the platform licenses it) and mute the original audio.</span></li>
      <li><b>Real tracks, licensed</b><span>Kenyan artists with permission, Pixabay Music, or CC&nbsp;BY tracks in <code>content/music</code>: picked automatically by mood (urgent or uplifting) and credited.</span></li>
      <li><b>Never</b><span>Popular songs baked into auto-posted videos: they get muted or taken down, and strikes hurt the account.</span></li>
      <li><b>Fallback</b><span>With no licensed track, an original synthesised bed: a tense pulse for civic posts, kalimba and benga for good news.</span></li>
    </ul>
  </section>

  <section id="quality" class="sec" aria-labelledby="t-quality">
    <p class="kicker">12</p><h2 id="t-quality">The quality bar</h2>
    <ol class="cards cards--num">
      <li><b>The guard</b><span>Clean and grown-up, lengths, sources, licensed photos, no name-calling, no campaigning, no tribe, no betting.</span></li>
      <li><b>The critic</b><span>A tough-editor pass scores hook, sendability, clarity, freshness, voice, craft, picture and hold. Under 7.5 is rewritten.</span></li>
      <li><b>Visual QA</b><span>Every render is measured: overflow, collisions, anything off the canvas, and every line of text checked for contrast against the real pixels behind it.</span></li>
      <li><b>Cost-free</b><span>The writer runs free on a Gemini API key. Photos come free from Wikimedia Commons and Pexels. Claude is optional, capped at $0.50 a week.</span></li>
    </ol>
  </section>

  <section id="launch" class="sec" aria-labelledby="t-launch">
    <p class="kicker">13</p><h2 id="t-launch">Launch set</h2>
    <p class="note">Rendered by the pipeline, ready to post. Full-size files are in <code>exports/posts/</code>. Once the Pexels key is set, the weekly posts arrive with real photos.</p>
    <div class="gallery">{gallery}</div>
    <h3 class="sub">Profiles</h3>
    <div class="profiles">{profiles}</div>
    <p class="handles">Handle everywhere: <b>{e(B['handle'])}</b> · Instagram · TikTok · Facebook · YouTube · X · WhatsApp Channel</p>
  </section>

  <section id="autopilot" class="sec sec--night" aria-labelledby="t-auto">
    <p class="kicker">14</p><h2 id="t-auto">Autopilot</h2>
    <p class="note">The self-running engine on GitHub Actions. Your part: about 15 minutes of taps a week.</p>
    <ol class="flow">{flow}</ol>
  </section>

  <section id="money" class="sec" aria-labelledby="t-money">
    <p class="kicker">15</p><h2 id="t-money">Keeping it alive</h2>
    <p class="note">Those who can pay, pay, so those who can't still learn for free.</p>
    <ul class="moneys">{money}</ul>
    <h3 class="sub">First 90 days</h3>
    <ol class="plan90">{plan90}</ol>
  </section>
</main>

<footer class="bookfoot">
  <p><b>Kenya on Record</b> brand book v3 · {e(B['tagline_en'])} · Built from <code>automation/</code>; re-run <code>build_book.py</code> after any brand change.</p>
</footer>
"""


CSS = f"""
:root{{--paper:{P['ink']['50']};--paper-2:{P['ink']['100']};--ink:{P['ink']['900']};--ink-2:{P['ink']['600']};--line:{P['ink']['200']};--card:#FFFFFF;
--sig:{P['shuka']['500']};--sig-ink:{P['shuka']['600']};--red:{P['shuka']['600']};--green:{P['chai']['700']};--night:{P['ink']['950']};--night-2:{P['ink']['900']};
--f-d:"Inter Tight","Arial Narrow",system-ui,sans-serif;--f-b:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;--paper:{P['ink']['950']};--paper-2:{P['ink']['900']};--ink:{P['ink']['50']};--ink-2:{P['ink']['300']};--line:{P['ink']['800']};--card:{P['ink']['900']};--sig-ink:{P['shuka']['400']}}}}}
:root[data-theme="dark"]{{color-scheme:dark;--paper:{P['ink']['950']};--paper-2:{P['ink']['900']};--ink:{P['ink']['50']};--ink-2:{P['ink']['300']};--line:{P['ink']['800']};--card:{P['ink']['900']};--sig-ink:{P['shuka']['400']}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font:400 17px/1.55 var(--f-b);padding-inline:clamp(16px,4vw,48px)}}
.book{{max-width:1120px;margin:0 auto}}
h1,h2,h3{{text-wrap:balance}}
code{{font:500 .86em ui-monospace,Consolas,monospace;background:var(--paper-2);padding:.08em .35em;border-radius:4px}}
.sr{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}
a{{color:var(--sig-ink)}}
:focus-visible{{outline:3px solid var(--sig);outline-offset:3px}}
.topbar{{position:sticky;top:0;z-index:5;background:var(--paper);margin-inline:calc(-1*clamp(16px,4vw,48px));padding:10px clamp(16px,4vw,48px);border-bottom:1px solid var(--line)}}
.toc{{max-width:1120px;margin:0 auto;display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}}
.toc a{{flex:none;padding:7px 10px;font:700 12px/1 var(--f-d);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);text-decoration:none}}
.toc a:hover{{color:var(--ink);box-shadow:inset 0 -2px 0 var(--sig)}}
.hero{{padding-block:72px 48px}}
.logo{{width:min(620px,100%);height:auto;display:block}}
.logo--dark{{display:none}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]) .logo--light{{display:none}}:root:not([data-theme="light"]) .logo--dark{{display:block}}}}
:root[data-theme="dark"] .logo--light{{display:none}}:root[data-theme="dark"] .logo--dark{{display:block}}
.tagline{{margin:22px 0 0;font:800 clamp(28px,4.4vw,48px)/1.05 var(--f-d);letter-spacing:-.025em}}
.tagline span{{color:var(--ink-2);font-weight:600}}
.lede{{max-width:58ch;font-size:19px;color:var(--ink-2);margin:16px 0 0}}
.kicker{{margin:0 0 6px;font:800 13px/1 var(--f-d);letter-spacing:.12em;text-transform:uppercase;color:var(--sig-ink)}}
.manifesto{{margin-inline:calc(-1*clamp(16px,4vw,48px));padding:56px clamp(16px,4vw,48px);background:var(--night);color:{P['ink']['50']}}}
.manifesto .kicker{{color:var(--sig);max-width:1120px;margin-inline:auto}}
.man-line{{max-width:1120px;margin:8px auto 0;font:900 clamp(44px,9vw,112px)/.95 var(--f-d);letter-spacing:-.04em}}
.man-sub{{max-width:1120px;margin:16px auto 0;color:{P['ink']['300']};font-size:19px}}
.sec{{padding-block:56px;border-top:1px solid var(--line)}}
.sec h2{{margin:0 0 16px;font:800 clamp(30px,4.6vw,48px)/1 var(--f-d);letter-spacing:-.03em}}
.note{{max-width:68ch;color:var(--ink-2);margin:0 0 22px}}
.note.small{{font-size:14.5px}}
.big{{max-width:46ch;font:700 clamp(21px,2.5vw,28px)/1.3 var(--f-d);letter-spacing:-.015em;margin:0 0 28px}}
.sub{{margin:34px 0 14px;font:800 13px var(--f-d);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-2)}}
.lbl{{font:800 12px var(--f-d);letter-spacing:.1em;text-transform:uppercase}}
.pillars,.cards,.lanes,.moneys,.plan90,.pairs{{list-style:none;margin:0;padding:0;display:grid;gap:0 28px}}
.pillars{{grid-template-columns:repeat(4,1fr)}}
.pillars li,.cards li,.lanes li,.moneys li{{padding:16px 0;border-top:2px solid var(--ink);display:flex;flex-direction:column;gap:6px}}
.pillars b{{font:800 24px var(--f-d);letter-spacing:-.02em}}
.pillars span,.cards span,.lanes span,.moneys p{{font-size:15px;line-height:1.45;color:var(--ink-2);margin:0}}
.cards{{grid-template-columns:repeat(4,1fr)}}
.cards--3{{grid-template-columns:repeat(3,1fr);margin-top:24px}}
.cards b,.lanes b{{font:800 17px var(--f-d);letter-spacing:-.01em}}
.cards--num{{counter-reset:n;grid-template-columns:repeat(4,1fr)}}
.cards--num li::before{{counter-increment:n;content:"0" counter(n);font:800 13px var(--f-d);letter-spacing:.08em;color:var(--sig-ink)}}
.logos{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.lg{{display:flex;align-items:center;justify-content:center;gap:24px;padding:34px 28px;min-height:160px;border-radius:4px}}
.lg-svg{{width:100%;max-width:400px;height:auto}}
.lg-ic{{width:96px;height:96px}}
.lg-stack{{width:120px;height:auto}}
.lg--paper{{background:{P['ink']['50']};box-shadow:inset 0 0 0 1px var(--line)}}.lg--night{{background:{P['ink']['950']}}}.lg--red{{background:{P['shuka']['600']}}}.lg--icons{{background:{P['ink']['900']}}}
.rules{{margin:20px 0 0;padding-left:20px;display:grid;gap:6px;max-width:72ch;color:var(--ink-2)}}
.ramps{{display:grid;gap:22px}}
.ramp{{display:grid;grid-template-columns:220px 1fr;gap:22px;align-items:start}}
.ramp-head h3{{margin:0;font:800 20px var(--f-d)}}
.ramp-head p{{margin:6px 0 0;font-size:14px;color:var(--ink-2)}}
.shades{{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(11,1fr);gap:4px}}
.shades li{{background:var(--c);color:var(--t);min-height:92px;padding:8px 7px;display:flex;flex-direction:column;justify-content:flex-end;gap:2px;border-radius:3px}}
.shades li.is-brand{{outline:3px solid var(--ink);outline-offset:2px}}
.shades b{{font:800 13px var(--f-d)}}
.shades code{{background:none;padding:0;color:inherit;font-size:10.5px}}
.pairs{{grid-template-columns:repeat(4,1fr);gap:12px}}
.pairs li{{display:flex;gap:12px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:4px}}
.pair-demo{{flex:none;width:52px;height:52px;display:grid;place-items:center;background:var(--b);color:var(--f);font:800 22px var(--f-d);border-radius:3px}}
.pairs b{{display:block;font:700 13.5px/1.3 var(--f-b)}}
.pairs small{{font-size:12.5px;color:var(--ink-2)}}
.types{{display:grid;gap:0}}
.ty{{padding:22px 0;border-top:1px solid var(--line)}}
.ty .lbl{{color:var(--ink-2)}}
.ty p{{margin:8px 0}}
.ty small{{color:var(--ink-2);font-size:14px}}
.ty-d{{font:800 clamp(34px,6vw,68px)/1 var(--f-d);letter-spacing:-.025em}}
.ty-l{{font:800 20px var(--f-d);letter-spacing:.1em;text-transform:uppercase;color:var(--sig-ink)}}
.ty-b{{font:500 21px/1.42 var(--f-b);max-width:46ch}}
.examples{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.ex{{margin:0}}.ex img{{width:100%;height:auto;display:block;border-radius:4px}}
.series{{list-style:none;margin:0;padding:0;display:grid}}
.series-row{{display:grid;grid-template-columns:110px 1fr 110px;gap:20px;align-items:center;padding:14px 0;border-top:1px solid var(--line)}}
.when{{font:800 13px/1.3 var(--f-d);letter-spacing:.04em;color:var(--sig-ink)}}
.series-row h3{{margin:0;font:800 18px/1.2 var(--f-d);letter-spacing:-.01em}}
.series-row p{{margin:4px 0 0;font-size:15px;color:var(--ink-2)}}
.series-row img{{width:110px;height:auto;border-radius:3px;display:block}}
.lanes{{grid-template-columns:repeat(4,1fr)}}
.doit{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.doit>div{{padding:20px 22px;border-radius:4px;color:#fff}}
.doit p{{margin:6px 0 0}}
.yes{{background:var(--green)}}.no{{background:var(--red)}}
.glossary{{margin:28px 0 0;display:grid;grid-template-columns:1fr 1fr;gap:0 28px}}
.gl{{display:grid;grid-template-columns:170px 1fr;gap:14px;padding:12px 0;border-top:1px solid var(--line)}}
.gl dt{{font:800 16px/1.2 var(--f-d)}}
.gl dt small{{display:block;margin-top:4px;font:700 11px var(--f-d);letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2)}}
.gl dd{{margin:0;font-size:15px;color:var(--ink-2)}}
.sec--night{{margin-inline:calc(-1*clamp(16px,4vw,48px));padding-inline:clamp(16px,4vw,48px);background:var(--night);color:{P['ink']['50']};border-top:none}}
.sec--night > *{{max-width:1120px;margin-left:auto;margin-right:auto}}
.sec--night .note,.sec--night .cards span{{color:{P['ink']['300']}}}
.sec--night .cards li{{border-top-color:var(--sig)}}
.sec--night .kicker{{color:var(--sig)}}
.sec--night a{{color:var(--sig)}}
.reels{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;max-width:760px;margin-bottom:24px}}
.reel{{margin:0}}.reel img{{width:100%;height:auto;border-radius:4px;display:block}}
.reel figcaption,.g-item figcaption{{margin-top:6px;font:500 12px ui-monospace,monospace;color:var(--ink-2);overflow-wrap:anywhere}}
.gallery{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;align-items:start}}
.g-item{{margin:0}}.g-item img{{width:100%;height:auto;display:block;border-radius:3px}}
.profiles{{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}}
.pf{{margin:0}}.pf img{{width:100%;height:auto;display:block;border-radius:3px}}
.pf--wide{{grid-column:1/-1}}
.pf--av img{{display:inline-block;width:140px;border-radius:50%;margin-right:10px}}
.pf figcaption{{margin-top:6px;font-size:13px;color:var(--ink-2)}}
.handles{{margin-top:18px;padding:12px 0;border-top:1px solid var(--line)}}
.flow{{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(7,1fr);gap:0 16px}}
.flow li{{padding:14px 0;border-top:2px solid {P['ink']['700']};display:flex;flex-direction:column;gap:6px}}
.flow li:nth-child(6){{border-top-color:var(--sig)}}
.flow b{{font:800 16px var(--f-d);color:var(--sig)}}
.flow span{{font-size:13.5px;line-height:1.45;color:{P['ink']['300']}}}
.f-when{{min-height:1.2em;font:800 11px var(--f-d)!important;letter-spacing:.1em;text-transform:uppercase;color:{P['ink']['400']}!important}}
.moneys{{grid-template-columns:repeat(5,1fr)}}
.m-tag{{font:800 11px var(--f-d);letter-spacing:.1em;text-transform:uppercase;color:var(--sig-ink)}}
.moneys h3{{margin:0;font:800 17px var(--f-d)}}
.plan90{{grid-template-columns:repeat(4,1fr)}}
.plan90 li{{padding:14px 0;border-top:2px solid var(--sig)}}
.plan90 p{{margin:6px 0 0;font-size:14.5px;color:var(--ink-2)}}
.bookfoot{{max-width:1120px;margin:40px auto 0;padding-block:24px 40px;border-top:1px solid var(--line);font-size:14px;color:var(--ink-2)}}
@media (max-width:980px){{.cards,.cards--num,.pillars,.lanes,.pairs{{grid-template-columns:repeat(2,1fr)}}.moneys{{grid-template-columns:repeat(2,1fr)}}.flow{{grid-template-columns:repeat(2,1fr)}}.plan90{{grid-template-columns:repeat(2,1fr)}}.gallery{{grid-template-columns:repeat(3,1fr)}}.glossary{{grid-template-columns:1fr}}.ramp{{grid-template-columns:1fr;gap:10px}}.cards--3{{grid-template-columns:repeat(2,1fr)}}}}
@media (max-width:620px){{.cards,.cards--num,.cards--3,.pillars,.lanes,.pairs,.moneys,.flow,.plan90,.logos,.doit,.profiles,.examples{{grid-template-columns:1fr}}.reels{{grid-template-columns:repeat(2,1fr)}}.gallery{{grid-template-columns:repeat(2,1fr)}}.shades{{grid-template-columns:repeat(6,1fr)}}.series-row{{grid-template-columns:1fr 84px}}.series-row .when{{grid-column:1/-1}}.series-row img{{width:84px}}.gl{{grid-template-columns:1fr;gap:4px}}.lg--icons{{flex-wrap:wrap}}}}
"""

FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@600;700;800;900&family=Inter:wght@400;500;600;700&display=swap">'


def main() -> None:
    body = build_body()
    head = f"<title>Kenya on Record Brand Book</title>\n{FONTS}\n<style>{CSS}</style>"
    out = ROOT / "brand-book"
    out.mkdir(exist_ok=True)
    if "--fragment" in sys.argv:
        (out / "artifact.html").write_text(head + "\n" + body, encoding="utf-8")
        print("wrote", out / "artifact.html")
    page = (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n{head}\n</head>\n'
            f'<body>\n{body}\n</body>\n</html>\n')
    (out / "index.html").write_text(page, encoding="utf-8")
    print("wrote", out / "index.html", f"({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
