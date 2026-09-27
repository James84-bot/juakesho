"""
build_book.py — builds the Jua Kesho brand book as one self-contained HTML file.

All graphics come from brandkit.py and the rendered exports, embedded inline,
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXP = ROOT / "exports"
LOGO = ROOT / "assets" / "logo"
CAL = json.loads((HERE / "calendar.json").read_text(encoding="utf-8"))
POSTS = json.loads((HERE / "content" / "posts.json").read_text(encoding="utf-8"))["posts"]
C, B = bk.C, bk.BRAND
e = html.escape


def img_uri(path: Path, width: int, quality: int = 78) -> str:
    im = Image.open(path).convert("RGB")
    im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def svg_inline(path: Path, cls: str = "", label: str = "") -> str:
    s = path.read_text(encoding="utf-8")
    s = s.replace("<svg ", f'<svg class="{cls}" role="img" aria-label="{e(label)}" ', 1)
    return s.replace(' width="', ' data-w="').replace(' height="', ' data-h="')


def mascot(expr: str, cls: str = "m") -> str:
    return f'<svg class="{cls}" viewBox="0 0 200 200" role="img" aria-label="Jua, {expr}">{bk.mascot(expr)}</svg>'


def shape(content: str, w: int, h: int, label: str, bg: str | None = None) -> str:
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg viewBox="0 0 {w} {h}" class="shape" role="img" aria-label="{e(label)}">'
            f'{bk.GLOW_DEFS}{rect}{content}</svg>')


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
EXPR_USE = {
    "happy": "Default. Intros, tips, good news.",
    "wink": "Decode, clever facts, inside jokes.",
    "wow": "Usiibiwe!, surprises, big reveals.",
    "thinking": "Questions, myths, polls.",
    "laugh": "Still in 2026? roasts, funny wins, community replies.",
    "cool": "Cap or No Cap? verdicts, confident how-tos.",
    "visor": "Kesho Mode: the future, AI, predictions.",
}

LANE_ICON_BG = {"campus": "jacaranda", "young_pro": "usiku", "creator": "waridi", "hustle": "chai",
                "techie": "ziwa", "diaspora": "pwani", "everyone": "jua"}

SERIES = [
    ("Mon 07:30", "AI Hack", "hack", "One move that saves real time. Built to be saved and sent to the group chat."),
    ("Tue 12:45", "Decode · Cap or No Cap? · Still in 2026?", "still", "The word everyone's saying, the claim everyone repeats, the outdated habit we roast (never a person)."),
    ("Wed 18:30", "Usiibiwe!", "usiibiwe", "The scams hitting young people right now: fake jobs, task scams, fake reversals."),
    ("Thu 19:30", "Vichekesho", "vichekesho", "Three-panel stick-cast comics. Relatable first, lesson second."),
    ("Fri 17:00", "Put Us On · Build With Me · POV: Kesho", "spotlight", "African artists, creators and startups; real builds; near-future POVs."),
    ("Sat 11:00", "Kesho Kutwa", "cover", "A 6-slide carousel on what's coming, in Kesho Mode, ending on a send."),
    ("Sun 18:00", "Jua Asks", "glasspoll", "A spicy-but-clean story poll. The answers pick next week's topics."),
]

GLOSSARY = [
    ("Jua", "noun · verb", "Sun, and to know. The mascot's name and the brand's whole idea: light that helps you know."),
    ("Kesho", "noun", "Tomorrow; the future. In the name and in <em>Kesho Mode</em>, the night look."),
    ("Kesho iko hapa", "tagline", "“Tomorrow is here.” Used as a sign-off and on every profile."),
    ("Wanakesho", "noun", "“The people of tomorrow”: the community. Never “followers” or “fans”."),
    ("Kesho kutwa", "series", "Literally “the day after tomorrow”; Kenyans use it for “someday”. Our future series."),
    ("Kamusi ya Kesho", "collection", "The community dictionary. Every Decode post is a numbered entry."),
    ("Vichekesho", "series", "\u201cComedies.\u201d Three-panel stick-cast comics: setup, turn, payoff. Always teaches one thing."),
    ("Usiibiwe!", "series", "“Don't get robbed!” Scam awareness. Always in Shuka red."),
    ("Anza sasa", "phrase", "“Start now.” The practical step that ends every future post."),
    ("Leo / Kesho", "pair", "Today / tomorrow. How every prediction is framed: what exists, what's coming."),
    ("Mchana / Usiku", "modes", "Day / night: the two visual moods. Bright cut-paper by day, orbits and circuits by night."),
    ("Kenyan English", "voice", "How we write: English sentences with everyday Kenyan words (eh, sasa, kindly, manze, sawa). Anyone in Kenya or abroad can follow."),
    ("Sasa!", "greeting", "Hi! How every intro and reel opens."),
]

MONEY = [
    ("Jua Class", "Paid workshops", "AI and automation sessions for companies, campuses and creators. Those who can pay, pay; that keeps the feed free for everyone."),
    ("Imeletwa na", "Clearly labelled brand deals", "Series and integrations with brands young Kenyans actually use: telcos, phones, fintech, edtech, fashion. Always labelled. Never betting, alcohol or predatory loans."),
    ("Kamusi ya Kesho", "Digital products", "The collected dictionary, printable guides and templates, sold cheaply via M-Pesa and free for schools."),
    ("Commissioned series", "Partners", "NGOs, counties and innovation programmes pay for explainer series on digital topics, in our voice, clearly credited."),
    ("Autopilot builds", "Services", "The same content engine, set up for other brands. It's James's own skill set, and each build funds more free content."),
]

DAY_90 = [
    ("Weeks 1–2", "Claim @juakesho everywhere. Set up profiles with the kit, the WhatsApp Channel and the Telegram bot. Post Karibu plus the first 5 posts by hand."),
    ("Weeks 3–6", "Switch on the autopilot: 7 posts a week, 15 minutes of approvals. Let the Sunday poll choose the next topic."),
    ("Weeks 7–10", "First Kesho Kutwa reels from the carousel scripts. Run a free pilot Jua Class for 20 small businesses and collect real feedback."),
    ("Weeks 11–13", "Build the sponsor deck from real reach and save numbers. Pitch one community radio station on the weekly 2-minute segment."),
]


def build_body() -> str:
    lock_light = svg_inline(LOGO / "wordmark-on-light.svg", "logo logo--light", "Jua Kesho")
    lock_dark = svg_inline(LOGO / "wordmark-on-dark.svg", "logo logo--dark", "Jua Kesho")

    swatches = "".join(
        f'<li class="sw" style="--c:{v["hex"]};--t:{v["text"]}"><span class="chip"><b>{k.capitalize()}</b><code>{v["hex"]}</code></span>'
        f'<span class="sw-txt">{e(v["meaning"])}</span></li>'
        for k, v in B["colors"].items())

    expressions = "".join(
        f'<figure class="ex">{mascot(x)}<figcaption><b>{x}</b><span>{e(u)}</span></figcaption></figure>'
        for x, u in EXPR_USE.items())

    day = [
        ("Blobs", bk.blob(90, 80, 60, C["jua"], 3) + bk.blob(200, 90, 45, C["jacaranda"], 7) + bk.blob(150, 40, 26, C["waridi"], 9)),
        ("Kanga band", bk.kanga_band(10, 55, 260, 40, [C["usiku"], C["jua"], C["shuka"], C["chai"], C["jacaranda"]], 4)),
        ("Squiggle & dots", bk.squiggle(20, 70, 240, C["shuka"], 5, amp=16, waves=4, width=10) + bk.dots(30, 110, 220, 30, C["pwani"], 2, n=10)),
        ("Tea leaf", bk.leaf(100, 80, 55, C["chai"], -25, 1) + bk.leaf(185, 90, 40, C["jua"], 30, 2)),
    ]
    night = [
        ("Orbits", f'<g transform="translate(95 20) scale(.45)">{bk.mascot("visor")}</g>' + bk.orbit(140, 70, 115, 36, -12, C["pwani"], 3, planets=2)),
        ("Circuit kanga", bk.circuit_kanga(10, 50, 260, 44, [C["jua"], C["pwani"], C["waridi"], C["jacaranda"]], 2)),
        ("Circuits", bk.circuit(10, 10, 260, 130, C["pwani"], 8, traces=6)),
        ("LED sun", bk.pixel_sun(140, 75, 48, cell=12, seed=3)),
    ]
    day_html = "".join(f'<figure class="dev">{shape(s, 280, 150, n)}<figcaption>{n}</figcaption></figure>' for n, s in day)
    night_html = "".join(f'<figure class="dev dev--night">{shape(s, 280, 150, n, C["usiku"])}<figcaption>{n}</figcaption></figure>' for n, s in night)

    series_rows = ""
    for when, name, tpl, what in SERIES:
        post = next((p for p in POSTS if p["template"] == tpl), None)
        thumb = f'<img src="{img_uri(EXP / "posts" / (post["id"] + ".png"), 220)}" alt="{e(name)} example" width="110" height="{275 if tpl == "poll" else 138}">' if post else ""
        series_rows += f'<li class="series-row"><span class="when">{when}</span><div><h3>{e(name)}</h3><p>{e(what)}</p></div>{thumb}</li>'

    lanes = "".join(
        f'<li class="lane" style="--c:{C[LANE_ICON_BG[k]]};--t:{B["colors"][LANE_ICON_BG[k]]["text"]}"><b>{k}</b><span>{e(v["who"])}</span><small>{e(v["voice"])}</small></li>'
        for k, v in CAL["lanes"].items())

    gallery = "".join(
        f'<figure class="g-item{" g-story" if p.get("size") == "story" else ""}"><img src="{img_uri(EXP / "posts" / (p["id"] + ".png"), 360)}" alt="{e(p["id"])}" width="360" height="{640 if p.get("size") == "story" else 450}"><figcaption>{e(p["id"])}</figcaption></figure>'
        for p in POSTS)

    profiles = (f'<figure class="pf pf--wide"><img src="{img_uri(EXP / "profiles" / "youtube-banner-2560x1440.png", 900)}" alt="YouTube banner" width="900" height="506"><figcaption>YouTube 2560×1440 · key content inside the safe zone</figcaption></figure>'
                f'<figure class="pf"><img src="{img_uri(EXP / "profiles" / "x-header-1500x500.png", 700)}" alt="X header" width="700" height="233"><figcaption>X header 1500×500</figcaption></figure>'
                f'<figure class="pf"><img src="{img_uri(EXP / "profiles" / "facebook-cover-1640x624.png", 700)}" alt="Facebook cover" width="700" height="266"><figcaption>Facebook cover 1640×624</figcaption></figure>'
                f'<figure class="pf pf--av"><img src="{img_uri(EXP / "profiles" / "avatar-jacaranda.png", 300)}" alt="Profile picture" width="150" height="150"><figcaption>Avatar · every platform</figcaption></figure>')

    glossary = "".join(f'<div class="gl"><dt>{e(w)}<small>{e(k)}</small></dt><dd>{d}</dd></div>' for w, k, d in GLOSSARY)
    money = "".join(f'<li class="money"><span class="m-tag">{e(t)}</span><h3>{e(n)}</h3><p>{e(d)}</p></li>' for n, t, d in MONEY)
    plan90 = "".join(f'<li><span class="when">{w}</span><p>{e(d)}</p></li>' for w, d in DAY_90)

    flow_steps = [
        ("Sun 17:00", "Plan", "calendar.json picks each day's series, lane and colour."),
        ("", "Draft", "AI writes the week in the Jua Kesho voice, fed with what worked last month."),
        ("", "Guard", "Clean-for-everyone, brand rules, length and source checks. Failures go back for one AI repair."),
        ("", "Design", "The renderer builds every post with its own irregular shapes."),
        ("You · 15 min", "Approve", "Each design arrives on Telegram with ✅ / ❌. Nothing posts without your tap."),
        ("Every 2 h", "Publish", "Approved posts go live on Instagram and Facebook at their time."),
        ("Weekly", "Learn", "Saves, shares and reach score every post and steer next week's draft."),
    ]
    flow = "".join(f'<li><span class="f-when">{e(w)}</span><b>{e(n)}</b><span>{e(d)}</span></li>' for w, n, d in flow_steps)

    cast_row = ""
    for who, meta in bk.CAST.items():
        fig = bk.stick(who, 90, 250, "stand", "happy")
        cast_row += (f'<figure class="cast"><svg viewBox="0 0 180 270" role="img" aria-label="{e(meta["label"])}">{fig}</svg>'
                     f'<figcaption><b>{e(meta["label"])}</b><span>{e(meta["who"])}</span></figcaption></figure>')
    pose_list = [("wave", "shosh", "happy"), ("point", "makanga", "happy"), ("think", "mama_mboga", "flat"),
                 ("cheer", "student", "happy"), ("walk", "pro", "happy"), ("phone", "boda", "worried"), ("shrug", "farmer", "worried")]
    poses = "".join(
        f'<figure class="pose"><svg viewBox="0 0 180 270" role="img" aria-label="{p} pose">{bk.stick(w, 90, 250, p, m, phone=(p == "phone"))}</svg><figcaption>{p}</figcaption></figure>'
        for p, w, m in pose_list)
    reel_strip = ""
    reel_dir = EXP / "reels"
    for pid in ("01-hack-lecture-notes", "05-vichekesho-cv", "14-money-idle-funds", "17-cant-wait"):
        cover = reel_dir / f"{pid}-cover.jpg"
        if cover.exists():
            reel_strip += f'<figure class="reel"><img src="{img_uri(cover, 300)}" alt="Reel: {pid}" width="150" height="267"><figcaption>{pid}.mp4</figcaption></figure>'
    if not reel_strip:
        reel_strip = '<p class="note">Run <code>python video.py</code> to render the Reels.</p>'
    comic_post = next((p for p in POSTS if p["template"] == "vichekesho"), None)
    comic = img_uri(EXP / "posts" / (comic_post["id"] + ".png"), 520) if comic_post else ""
    stickers = ""
    for f in sorted((EXP / "stickers").glob("*.webp")):
        im = Image.open(f).convert("RGBA").resize((200, 200), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=80)
        stickers += f'<img src="data:image/webp;base64,{base64.b64encode(buf.getvalue()).decode()}" alt="{f.stem} sticker" width="100" height="100">'

    return f"""
<header class="top">
  <nav class="toc" aria-label="Sections">
    <a href="#idea">Idea</a><a href="#jua">Jua</a><a href="#cast">Cast</a><a href="#logo">Logo</a><a href="#colour">Colour</a><a href="#type">Type</a>
    <a href="#shapes">Shapes</a><a href="#series">Series</a><a href="#lanes">Audience</a><a href="#more">Want more</a>
    <a href="#trend">Trends</a><a href="#see">See Through It</a><a href="#motion">Motion</a><a href="#quality">Quality</a><a href="#lore">Lore</a><a href="#drops">Drops</a><a href="#voice">Dictionary</a><a href="#launch">Launch</a><a href="#autopilot">Autopilot</a><a href="#money">Money</a>
  </nav>
</header>

<main class="book">
  <section class="hero" aria-labelledby="t-hero">
    <div class="hero-copy">
      <p class="hand hero-hi">Sasa, Wanakesho!</p>
      <h1 id="t-hero">{lock_light}{lock_dark}<span class="sr">Jua Kesho</span></h1>
      <p class="tag">{e(B['tagline_sw'])}</p>
      <p class="lede">A faceless Kenyan content brand for young people who live online: sharp, educated, always scrolling, and not yet tapping into AI and the future. Not a school. Hacks, takes, comics and drops that make them the first in their circle to know.</p>
      <p class="meaning"><b>jua</b> <span>= the sun</span> <b>+</b> <span>to know</span> &nbsp;·&nbsp; <b>kesho</b> <span>= tomorrow</span></p>
    </div>
    <div class="hero-art" aria-hidden="true">{mascot('happy', 'm m--hero')}</div>
  </section>

  <section class="manifesto" aria-label="Manifesto">
    <p class="man-kicker hand">the manifesto</p>
    <p class="man-line">Africa can't wait.</p>
    <p class="man-sub">Not for permission. Not for &ldquo;next year&rdquo;. Tomorrow is already here, and it belongs to whoever learns it first. Wake up. Build. Do it right.</p>
  </section>

  <section id="idea" class="sec" aria-labelledby="t-idea">
    <h2 id="t-idea"><i class="mk" style="--c:{C['jua']}"></i>The idea</h2>
    <p class="big">The future belongs to the young, and most of them are one good post away from using it. Jua Kesho is the account they send to their friends: funny, fast, Kenyan, and always one step ahead.</p>
    <ul class="pillars">
      <li style="--c:{C['jacaranda']}"><b>Know</b><span>One clear idea per post. Useful the same day.</span></li>
      <li style="--c:{C['shuka']}"><b>Laugh</b><span>Funny through situations and analogies, never at people.</span></li>
      <li style="--c:{C['chai']}"><b>Belong</b><span>The Wanakesho: everyone welcome, every continent invited.</span></li>
      <li style="--c:{C['usiku']}"><b>Clean</b><span>Edgy about ideas, never dirty, never cruel. Safe to share anywhere.</span></li>
    </ul>
    <div class="modes">
      <div class="mode mode--day"><span class="hand">Mchana mode</span><p>Daytime. Milk paper, sun-bright colours and hand-cut shapes. Warm, playful, of the soil.</p></div>
      <div class="mode mode--night"><span class="hand">Usiku · Kesho Mode + Glass</span><p>Night-time. Frosted-glass cards over glowing colour clouds, orbits and circuits: African tradition wired into tomorrow. The main look for hacks, takes and the future.</p></div>
    </div>
  </section>

  <section id="jua" class="sec" aria-labelledby="t-jua">
    <h2 id="t-jua"><i class="mk" style="--c:{C['shuka']}"></i>Meet Jua</h2>
    <p class="note">The host of a faceless brand. A sun whose rays are every colour in the palette: one light, many people. Jua never mocks, always explains, and changes expression to match the post.</p>
    <div class="exprs">{expressions}</div>
  </section>

  <section id="cast" class="sec" aria-labelledby="t-cast">
    <h2 id="t-cast"><i class="mk" style="--c:{C['udongo']}"></i>The stick cast</h2>
    <p class="note">Faceless, but human. A stick figure has no skin tone, body type or bank balance, so everyone from the boardroom to the boda stage sees themselves in it. Each character is recognised by props and colour. All of them share one skeleton, so they move with real human proportions in every post.</p>
    <div class="cast-row">{cast_row}</div>
    <h3 class="sub">Poses</h3>
    <div class="pose-row">{poses}</div>
    <div class="comic-demo">
      <img src="{comic}" alt="Vichekesho comic: Mama Mboga spots a fake 'sent by mistake' SMS" width="520" height="650">
      <div><span class="hand">Vichekesho</span><p>Three panels: setup, turn, payoff. Speech bubbles point at heads and SMS bubbles point at phones, placed automatically. The AI only writes who says what; the layout takes care of itself.</p></div>
    </div>
  </section>

  <section id="logo" class="sec" aria-labelledby="t-logo">
    <h2 id="t-logo"><i class="mk" style="--c:{C['jacaranda']}"></i>Logo</h2>
    <p class="note">Lowercase <b>jua kesho</b> in Unbounded ExtraBold, set close. The dot of the <b>j</b> is a tiny sun: the one piece of colour in the wordmark. Files are outlined SVGs in <code>assets/logo/</code>.</p>
    <div class="logos">
      <div class="lg lg--paper">{svg_inline(LOGO / 'wordmark-on-light.svg', 'lg-svg', 'Wordmark on light')}</div>
      <div class="lg lg--night">{svg_inline(LOGO / 'wordmark-on-dark.svg', 'lg-svg', 'Wordmark on dark')}</div>
      <div class="lg lg--jac">{svg_inline(LOGO / 'wordmark-on-dark.svg', 'lg-svg', 'Wordmark on jacaranda')}</div>
      <div class="lg lg--stack">{svg_inline(LOGO / 'stacked-on-light.svg', 'lg-svg lg-svg--stack', 'Stacked logo')}</div>
    </div>
    <ul class="rules">
      <li>Keep a clear space the size of the sun-dot around the wordmark.</li>
      <li>Wordmark minimum width 120 px. Smaller than that, use Jua (the icon) instead.</li>
      <li>Never recolour the letters with accents, add shadows or gradients, or stretch it.</li>
    </ul>
  </section>

  <section id="colour" class="sec" aria-labelledby="t-colour">
    <h2 id="t-colour"><i class="mk" style="--c:{C['chai']}"></i>Colour</h2>
    <p class="note">Named in Kiswahili after things every Kenyan knows. Each chip shows its approved text colour, and every pair passes WCAG AA contrast for text at post sizes.</p>
    <ul class="swatches">{swatches}</ul>
  </section>

  <section id="type" class="sec" aria-labelledby="t-type">
    <h2 id="t-type"><i class="mk" style="--c:{C['ziwa']}"></i>Type</h2>
    <div class="types">
      <div class="ty"><span class="lbl">Unbounded · display</span><p class="ty-d">Kesho iko hapa.</p><small>Headlines, words, numbers. Wide and confident, it reads well from far away on a small screen.</small></div>
      <div class="ty"><span class="lbl">Figtree · body</span><p class="ty-b">A computer that has learnt from millions of examples, so now it can guess the answer.</p><small>Explanations, steps, captions. Friendly and very readable.</small></div>
      <div class="ty"><span class="lbl">Caveat · hand notes</span><p class="ty-h">like the makanga who knows your stage!</p><small>Asides, jokes and punchlines, like someone scribbled on the poster.</small></div>
    </div>
  </section>

  <section id="shapes" class="sec" aria-labelledby="t-shapes">
    <h2 id="t-shapes"><i class="mk" style="--c:{C['waridi']}"></i>Shapes</h2>
    <p class="note">Nothing is a perfect circle or a plain rectangle. Every post generates its own irregular composition from a seed, so no two look alike, and the same post always renders the same way.</p>
    <h3 class="sub">Mchana</h3><div class="devs">{day_html}</div>
    <h3 class="sub">Usiku · Kesho Mode</h3><div class="devs">{night_html}</div>
  </section>

  <section id="series" class="sec" aria-labelledby="t-series">
    <h2 id="t-series"><i class="mk" style="--c:{C['udongo']}"></i>The week</h2>
    <p class="note">Seven series, each owning a day and a time. When a series owns a day, people start waiting for it.</p>
    <ul class="series">{series_rows}</ul>
  </section>

  <section id="lanes" class="sec" aria-labelledby="t-lanes">
    <h2 id="t-lanes"><i class="mk" style="--c:{C['pwani']}"></i>Who it's for</h2>
    <p class="note">Young, online, sharp. Each post is written for one <b>lane</b>, and lanes rotate week by week. Every industry gets covered through the tech angle: {', '.join(CAL.get('industries', []))}.</p>
    <ul class="lanes">{lanes}</ul>
    <h3 class="sub">Where they are</h3>
    <ul class="reach">
      <li><b>TikTok &amp; Reels</b><span>Discovery. Carousels become 20–30s slideshows with a voice-over script every week.</span></li>
      <li><b>Instagram carousels</b><span>Saves and sends. The highest engagement rate of any format.</span></li>
      <li><b>WhatsApp Channel &amp; stickers</b><span>Where Kenya actually talks. Stickers travel further than posts.</span></li>
      <li><b>X</b><span>Hot takes and threads: the Cap or No Cap? and Still in 2026? formats.</span></li>
    </ul>
  </section>

  <section id="more" class="sec" aria-labelledby="t-more">
    <h2 id="t-more"><i class="mk" style="--c:{C['jua']}"></i>Want more</h2>
    <p class="note">How the content keeps people coming back. The AI drafter is told to do all of these every week.</p>
    <ol class="hooks">
      <li><b>Rituals</b><span>Same series, same day, same time: <em>Jumatano ni Usiibiwe.</em></span></li>
      <li><b>Open loops</b><span>Every caption teases the next post. Carousels end on a question the next one answers.</span></li>
      <li><b>Collecting</b><span>Every Decode is a numbered entry in <em>Kamusi ya Kesho</em>. People want the full set.</span></li>
      <li><b>Say in it</b><span>Sunday's poll picks topics, Shosh's questions come from followers, and replies get featured.</span></li>
      <li><b>Real payoff</b><span>One thing you can use or share today, every post. Hype without payoff kills trust.</span></li>
      <li><b>It learns</b><span>Saves, shares and reach score each post, and what worked shapes next week automatically.</span></li>
    </ol>
  </section>

  <section id="trend" class="sec sec--night" aria-labelledby="t-trend">
    <h2 id="t-trend"><i class="mk" style="--c:{C['jua']}"></i>Trend playbook</h2>
    <p class="note">What the platforms reward in 2026, and how every post is built to match. The AI drafter follows these rules every week.</p>
    <ul class="play">
      <li><b>Hook in under 2 seconds</b><span>Instagram guidance points to the first ~1.7 seconds; TikTok to the first 3. Our hooks are 7 words max, in the Caveat hand, top of every design.</span></li>
      <li><b>Design for sends</b><span>DM shares carry several times the weight of likes for reaching non-followers. Every caption names who to send it to.</span></li>
      <li><b>Saves &amp; shares over likes</b><span>On TikTok, saves and shares now outrank likes. Hacks and steps get saved; takes get shared.</span></li>
      <li><b>Carousels with cliffhangers</b><span>The highest engagement rate of any Instagram format. Slide 1 forces the swipe; the last slide asks for a send.</span></li>
      <li><b>Searchable</b><span>Keywords in titles, on-screen text and captions: people search TikTok and Instagram like Google.</span></li>
      <li><b>Original only</b><span>Reposts and watermarks get cut from recommendations. Everything here is made by our own renderer.</span></li>
      <li><b>Ride trends safely</b><span>A daily Google Trends feed for Kenya, Nigeria, South Africa and the US. Politics, tragedy and betting are filtered out automatically; at most 2 trend-jacks a week, only with a real tech angle.</span></li>
      <li><b>Edutainment</b><span>Teach one thing, make it fun. It's the most reliable route to the share button.</span></li>
    </ul>
    <p class="note small">Sources: <a href="https://www.dataslayer.ai/blog/instagram-algorithm-2025-complete-guide-for-marketers">Dataslayer on Mosseri's ranking signals</a> · <a href="https://sproutsocial.com/insights/tiktok-algorithm/">Sprout Social on the TikTok algorithm</a> · <a href="https://www.contentgrip.com/brands-thriving-with-gen-z/">ContentGrip on Gen Z brands</a> · <a href="https://trends.google.com/trending?geo=KE">Google Trends, Kenya</a></p>
  </section>

  <section id="lore" class="sec" aria-labelledby="t-lore">
    <h2 id="t-lore"><i class="mk" style="--c:{C['waridi']}"></i>Lore &amp; running jokes</h2>
    <p class="note">Brands Gen Z loves behave like fandoms: characters with backstories, inside jokes, drops. Ours are below. The drafter keeps these going week to week.</p>
    <ul class="lore">
      <li><b>Jua's origin</b><span>The sun has been shining for about 4.6 billion years and only just discovered the internet. Wildly optimistic, terrible at hiding excitement, allergic to scams.</span></li>
      <li><b>Jua vs Mvua</b><span>The Nairobi rain keeps "cancelling Jua's plans". Every rainy week, Jua posts from "behind the clouds".</span></li>
      <li><b>Shosh, Jua's biggest fan</b><span>Forwards every post to 12 WhatsApp groups within a minute. Occasionally out-smarts the Techie.</span></li>
      <li><b>Application no. 41</b><span>The Student is always on their next job application. The count keeps going up until the day they land one, which becomes a celebration post.</span></li>
      <li><b>"It's actually simple"</b><span>The Techie's catchphrase, right before explaining something in far too much detail.</span></li>
      <li><b>The Makanga knows every route</b><span>...including data routes, cloud stages and how packets "alight".</span></li>
    </ul>
  </section>

  <section id="critique" class="sec" aria-labelledby="t-crit">
    <h2 id="t-crit"><i class="mk" style="--c:{C['shuka']}"></i>Critique without cruelty</h2>
    <div class="doit">
      <div class="yes"><span class="hand">Roast this</span><p>Outdated habits, slow processes, bad tech, scams, the old way. &ldquo;It's 2026 and we still&hellip;&rdquo;, followed by the upgrade that exists today.</p></div>
      <div class="no"><span class="hand">Never this</span><p>People, named artists, groups, regions or politicians. No &ldquo;stupid&rdquo;, no &ldquo;Africans are&hellip;&rdquo;. The joke is always on the old way.</p></div>
    </div>
    <p class="note" style="margin-top:18px">&ldquo;Africans don't support their own&rdquo; gets answered with action. <b>Put Us On</b> spotlights real African artists, creators and startups every other Friday, always with something to do: stream, follow, share.</p>
  </section>

  <section id="drops" class="sec" aria-labelledby="t-drops">
    <h2 id="t-drops"><i class="mk" style="--c:{C['jacaranda']}"></i>Drops</h2>
    <p class="note">Things people collect and pass on. The first drop is a 12-sticker WhatsApp pack, generated by <code>stickers.py</code> to WhatsApp's spec (512&times;512 WebP, under 100&nbsp;KB each, with a tray icon).</p>
    <div class="stickers">{stickers}</div>
    <ul class="reach" style="margin-top:18px">
      <li><b>Kamusi ya Kesho</b><span>Every Decode is a numbered card. 52 a year. Collect them all.</span></li>
      <li><b>Wanakesho of the Week</b><span>The best comment gets featured in Sunday's story.</span></li>
      <li><b>Build With Me breakdowns</b><span>Comment BOT, get the step-by-step. Sends people into the DMs.</span></li>
    </ul>
  </section>

  <section id="see" class="sec sec--night" aria-labelledby="t-see">
    <h2 id="t-see"><i class="mk" style="--c:{C['chai']}"></i>See Through It</h2>
    <p class="note">The hard stuff, told symbolically. Young Kenyans already feel it: money that disappears, trends that are bought, crowds that are paid, faith that gets exploited. We teach them to see the machine, and we never point at a person.</p>
    <ul class="play">
      <li><b>Follow the Money</b><span>One public number, what it means, how to check it yourself. The Auditor-General reported Sh304.4bn (59%) idle across 14 flagship projects over five years.</span></li>
      <li><b>Bought trends</b><span>Researchers documented Kenyan influencers paid about $10&ndash;15 a day over M-Pesa to push hashtags, coordinated in WhatsApp groups. We show how to spot one in 30 seconds.</span></li>
      <li><b>The Ksh 500 "job"</b><span>Allegory comics about being hired as someone's crowd or muscle. Fictional characters, real pattern, and a better offer: your future.</span></li>
      <li><b>Faith, protected</b><span>Never an attack on belief. We expose the tactics exploiters use (pay-for-a-miracle, isolation, fear, "stop your medicine") so believers can protect each other.</span></li>
      <li><b>Archetypes, not people</b><span><b>Bwana Ahadi</b> ("Mr Promise") stands for anyone who promises big and delivers little. Never drawn to resemble a real person.</span></li>
      <li><b>Sourced or silent</b><span>Every civic number carries a public source, and the checker blocks civic posts without one.</span></li>
      <li><b>Never tribe</b><span>Not in any direction. Kenyan English and Sheng belong to everyone. Unity is the point.</span></li>
      <li><b>Stay safe</b><span>Kenya's 2025 cybercrime amendments carry heavy penalties and vague terms. Systems-not-people keeps the account (and you) on solid ground.</span></li>
    </ul>
    <p class="note small">Sources: <a href="https://capitalfm.africa/audit-exposes-sh304bn-in-idle-govt-project-funds/">Capital FM on the Auditor-General's Sh304bn finding</a> · <a href="https://ieakenya.or.ke/blog/wasted-billions-kenyas-stalled-projects-expose-deep-flaws-in-budget-planning-and-execution/">IEA Kenya on stalled projects</a> · <a href="https://www.mozillafoundation.org/en/blog/fellow-research-inside-the-shadowy-world-of-disinformation-for-hire-in-kenya/">Mozilla on disinformation-for-hire</a> · <a href="https://www.hrw.org/news/2025/11/07/kenya-new-cybercrime-amendments-threaten-online-expression">HRW on the 2025 cybercrime amendments</a></p>
  </section>

  <section id="motion" class="sec" aria-labelledby="t-motion">
    <h2 id="t-motion"><i class="mk" style="--c:{C['ziwa']}"></i>Motion & sound</h2>
    <p class="note">Every design also ships as a 9:16 Reel/TikTok. Headlines land word by word, glass slides in, stickers pop, Jua bobs, colour drifts. The hook is on screen from frame zero. Content sits inside the platform safe zone, clear of the buttons and caption. Frames are stepped one by one, so every render is identical.</p>
    <div class="reels">{reel_strip}</div>
    <ul class="reach" style="margin-top:18px">
      <li><b>The Jua chime</b><span>A three-note kalimba sonic logo, rising like a sunrise. It opens every Reel.</span></li>
      <li><b>Original beat</b><span>A kalimba bed in A-pentatonic, synthesised in code: no licences, and it counts as original audio.</span></li>
      <li><b>Trending sound?</b><span>On TikTok, swap in a trending sound in-app when you post. The strongest move there.</span></li>
      <li><b>Pacing</b><span>6&ndash;14 seconds, sized to reading speed so people finish and replay.</span></li>
    </ul>
  </section>

  <section id="quality" class="sec" aria-labelledby="t-quality">
    <h2 id="t-quality"><i class="mk" style="--c:{C['jua']}"></i>The quality bar</h2>
    <p class="note">Three gates between an idea and your feed. Nothing reaches Telegram for approval without passing all three.</p>
    <ol class="hooks">
      <li><b>The guard</b><span>Clean for everyone, brand rules, lengths, sources, no named people in civic posts, no tribe, no betting.</span></li>
      <li><b>The critic</b><span>A tough-editor AI scores hook, sendability, clarity, freshness, voice and craft. Under 7.5 gets one rewrite, kept only if it scores higher. The score shows on your approval card.</span></li>
      <li><b>Visual QA</b><span>Every render is measured: text wider than its box, collisions, anything off the canvas. Broken designs are held for a human.</span></li>
    </ol>
  </section>

  <section id="voice" class="sec" aria-labelledby="t-voice">
    <h2 id="t-voice"><i class="mk" style="--c:{C['jacaranda']}"></i>Brand dictionary</h2>
    <dl class="glossary">{glossary}</dl>
    <div class="doit">
      <div class="yes"><span class="hand">Say it like this</span><p>&ldquo;Got a &lsquo;money sent by mistake&rsquo; SMS? Eh, check your M-PESA balance first.&rdquo;</p></div>
      <div class="no"><span class="hand">Never like this</span><p>&ldquo;People from [place] are the ones who steal.&rdquo; No blaming groups. We explain the trick, never who&rsquo;s behind it.</p></div>
    </div>
    <h3 class="sub">Tones toolbox</h3>
    <ul class="lore">
      <li><b>Sarcasm &amp; deadpan</b><span>&ldquo;Only Sh304bn idle. Minor.&rdquo; Lands because the number underneath is real and sourced.</span></li>
      <li><b>Irony &amp; exaggeration</b><span>&ldquo;It's 2026 and we still queue four hours to hear &lsquo;come tomorrow&rsquo;.&rdquo;</span></li>
      <li><b>Parody</b><span>Fake ads, fake launches, mock awards: &ldquo;Introducing The Queue&trade;, now with extra waiting.&rdquo; Always clearly labelled parody.</span></li>
      <li><b>Hype</b><span>Go loud for African wins. Put Us On is a celebration.</span></li>
      <li><b>Warmth</b><span>Sincere when someone could get hurt: scams, faith exploitation.</span></li>
      <li><b>The rule</b><span>Punch up (systems, tactics, the powerful, outdated habits), never down (victims, ordinary people, groups).</span></li>
    </ul>
    <ul class="rules">
      <li>Clean for everyone: no swearing in any language, nothing sexual, no alcohol, drugs or betting.</li>
      <li>No politics, politicians, tribes or religious debate. We are for all Kenyans and all people.</li>
      <li>Write in Kenyan English. Kenyan words season the sentence; they don't replace it.</li>
      <li>Every year, number or price carries a source. If we're not sure, we leave it out.</li>
      <li>Max three hashtags: always <b>#JuaKesho</b> plus the series tag.</li>
    </ul>
  </section>

  <section id="launch" class="sec" aria-labelledby="t-launch">
    <h2 id="t-launch"><i class="mk" style="--c:{C['shuka']}"></i>Launch set</h2>
    <p class="note">The first twelve designs, rendered by the pipeline and ready to post. Tap-size previews; full-size files are in <code>exports/posts/</code>.</p>
    <div class="gallery">{gallery}</div>
    <h3 class="sub">Profiles</h3>
    <div class="profiles">{profiles}</div>
    <p class="handles">Handle everywhere: <b>{e(B['handle'])}</b> · Instagram · TikTok · Facebook · YouTube · X · WhatsApp Channel</p>
  </section>

  <section id="autopilot" class="sec sec--night" aria-labelledby="t-auto">
    <h2 id="t-auto"><i class="mk" style="--c:{C['pwani']}"></i>Autopilot</h2>
    <p class="note">The self-running content engine. It runs in the cloud on GitHub Actions, so it doesn't depend on one laptop. Your part: about 15 minutes of taps a week.</p>
    <ol class="flow">{flow}</ol>
    <p class="note small">Automatic: Instagram and Facebook. Semi-automatic, with a Telegram reminder: WhatsApp Channel (no public posting API), TikTok/Reels voice-overs, radio and SMS scripts.</p>
  </section>

  <section id="money" class="sec" aria-labelledby="t-money">
    <h2 id="t-money"><i class="mk" style="--c:{C['chai']}"></i>Keeping it alive</h2>
    <p class="note">The rule: <b>those who can pay, pay, so those who can't still learn for free.</b> Running costs are small: GitHub is free at this volume, and AI drafting is a small monthly API bill. Check current pricing before relying on it.</p>
    <ul class="moneys">{money}</ul>
    <h3 class="sub">First 90 days</h3>
    <ol class="plan90">{plan90}</ol>
  </section>
</main>

<footer class="foot">
  {mascot('wink', 'm m--foot')}
  <p><b>Jua Kesho</b> brand book v1 · {e(B['tagline_sw'])} · Built from <code>automation/</code>. Re-run <code>build_book.py</code> after any brand change.</p>
</footer>
"""


CSS = """
:root{--paper:#FFF4E0;--paper-2:#FBE9C8;--ink:#1D1433;--ink-2:#4A3F5C;--line:#E7D5B3;--card:#FFFBF3;
--jua:#FFC629;--shuka:#D4301F;--jac:#7A4FD8;--chai:#0E7C50;--ziwa:#1E8FD6;--pwani:#15B8A6;--waridi:#FF7AB6;--udongo:#B8532A;--night:#1D1433;--night-2:#2A1F45;
--accent-ink:#5B34C7;--f-d:"Unbounded","Arial Black",system-ui,sans-serif;--f-b:"Figtree",system-ui,-apple-system,"Segoe UI",sans-serif;--f-h:"Caveat","Comic Sans MS",cursive}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--paper:#150E26;--paper-2:#1F1636;--ink:#FFF4E0;--ink-2:#CFC3E0;--line:#35294F;--card:#1F1636;--accent-ink:#B9A2FF}}
:root[data-theme="dark"]{color-scheme:dark;--paper:#150E26;--paper-2:#1F1636;--ink:#FFF4E0;--ink-2:#CFC3E0;--line:#35294F;--card:#1F1636;--accent-ink:#B9A2FF}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:400 17px/1.55 var(--f-b);padding-inline:clamp(16px,4vw,48px)}
.book{max-width:1120px;margin:0 auto}
h1,h2,h3{text-wrap:balance}
code{font:500 .88em ui-monospace,Consolas,monospace;background:var(--paper-2);padding:.08em .35em;border-radius:5px}
.hand{font-family:var(--f-h);font-weight:700}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
a{color:var(--accent-ink)}
:focus-visible{outline:3px solid var(--jac);outline-offset:3px;border-radius:6px}

.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--paper);margin-inline:calc(-1*clamp(16px,4vw,48px));padding:10px clamp(16px,4vw,48px);border-bottom:2px solid var(--line)}
.toc{max-width:1120px;margin:0 auto;display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}
.toc a{flex:none;padding:6px 12px;border-radius:999px;font:700 13px/1 var(--f-d);letter-spacing:-.01em;color:var(--ink);text-decoration:none;background:var(--paper-2)}
.toc a:hover{background:var(--jua);color:#1D1433}

.hero{display:grid;grid-template-columns:1.25fr .75fr;gap:32px;align-items:center;padding-block:56px 40px}
.hero-hi{margin:0;font-size:40px;color:var(--accent-ink);transform:rotate(-3deg);transform-origin:left}
.hero h1{margin:6px 0 0}
.logo{width:min(560px,100%);height:auto;display:block}
.logo--dark{display:none}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .logo--light{display:none}:root:not([data-theme="light"]) .logo--dark{display:block}}
:root[data-theme="dark"] .logo--light{display:none}:root[data-theme="dark"] .logo--dark{display:block}
.tag{margin:14px 0 0;font:800 clamp(26px,4vw,40px)/1.05 var(--f-d);letter-spacing:-.03em}
.lede{max-width:56ch;font-size:19px;color:var(--ink-2)}
.meaning{display:inline-flex;flex-wrap:wrap;gap:6px;align-items:baseline;margin:6px 0 0;padding:10px 16px;border-radius:40px 18px 36px 14px;background:var(--jua);color:#1D1433;font-size:16px}
.meaning b{font-family:var(--f-d);font-size:15px}
.hero-art{display:grid;place-items:center}
.m{width:100%;height:auto;display:block}
.m--hero{max-width:340px;animation:bob 6s ease-in-out infinite}
@keyframes bob{50%{transform:translateY(-8px) rotate(3deg)}}
@media (prefers-reduced-motion:reduce){.m--hero{animation:none}}

.sec{padding-block:56px;border-top:2px dashed var(--line)}
.sec h2{display:flex;align-items:center;gap:14px;margin:0 0 14px;font:800 clamp(28px,4.4vw,44px)/1 var(--f-d);letter-spacing:-.035em}
.mk{flex:none;width:34px;height:30px;background:var(--c);border-radius:58% 42% 63% 37% / 45% 58% 42% 55%;transform:rotate(-8deg)}
.note{max-width:66ch;color:var(--ink-2);margin:0 0 22px}
.note.small{font-size:15px}
.big{max-width:48ch;font:600 clamp(20px,2.4vw,26px)/1.4 var(--f-b);margin:0 0 28px}
.sub{margin:30px 0 14px;font:800 18px var(--f-d);letter-spacing:-.02em}

.pillars{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.pillars li{padding:18px;border-radius:22px 38px 18px 30px;background:var(--c);color:#fff;display:flex;flex-direction:column;gap:6px}
.pillars b{font:800 22px var(--f-d);letter-spacing:-.02em}
.pillars span{font-size:15px;line-height:1.4}
.modes{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}
.mode{padding:22px 24px;border-radius:30px 16px 34px 20px}
.mode .hand{font-size:32px}
.mode p{margin:4px 0 0}
.mode--day{background:var(--jua);color:#1D1433}
.mode--night{background:#1D1433;color:#FFF4E0;box-shadow:inset 0 0 0 2px #15B8A6}
.mode--night .hand{color:#15B8A6}

.exprs{display:grid;grid-template-columns:repeat(7,1fr);gap:12px}
.ex{margin:0;padding:12px;border-radius:24px;background:var(--card);border:2px solid var(--line);display:flex;flex-direction:column;gap:6px}
.ex figcaption{display:flex;flex-direction:column;gap:2px;font-size:13px;line-height:1.35;color:var(--ink-2)}
.ex b{font:800 14px var(--f-d);color:var(--ink)}

.cast-row{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
.cast{margin:0;padding:10px;border-radius:22px;background:var(--card);border:2px solid var(--line);display:flex;flex-direction:column;gap:6px}
.cast svg,.pose svg{width:100%;height:auto;display:block}
.cast figcaption{display:flex;flex-direction:column;gap:2px;font-size:13px;line-height:1.35;color:var(--ink-2)}
.cast b{font:800 14px var(--f-d);color:var(--ink)}
.pose-row{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
.pose{margin:0;padding:6px;border-radius:18px;background:#FFF4E0}
.pose figcaption{text-align:center;font:700 12px var(--f-b);color:#1D1433}
.comic-demo{display:grid;grid-template-columns:minmax(0,340px) 1fr;gap:24px;align-items:center;margin-top:24px}
.comic-demo img{width:100%;height:auto;border-radius:14px;display:block}
.comic-demo .hand{font-size:40px;color:var(--accent-ink)}
.comic-demo p{margin:4px 0 0;max-width:46ch;color:var(--ink-2)}
.play{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.play li{padding:16px;border-radius:22px;background:rgba(255,255,255,.08);border:1.5px solid rgba(255,255,255,.25);display:flex;flex-direction:column;gap:6px}
.play b{font:800 16px var(--f-d);color:#FFC629}
.play span{font-size:14px;line-height:1.45;color:#E9E1F5}
.sec--night a{color:#15B8A6}
.lore{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.lore li{padding:16px 18px;border-radius:26px 14px 28px 16px;background:var(--card);border:2px solid var(--line);display:flex;flex-direction:column;gap:6px}
.lore b{font:800 16px var(--f-d)}
.lore span{font-size:14.5px;color:var(--ink-2)}
.stickers{display:flex;flex-wrap:wrap;gap:10px;padding:18px;border-radius:24px;background:repeating-conic-gradient(var(--paper-2) 0 25%,var(--card) 0 50%) 0 0/28px 28px}
.stickers img{width:100px;height:100px}
.manifesto{margin-inline:calc(-1*clamp(16px,4vw,48px));padding:48px clamp(16px,4vw,48px);background:#1D1433;color:#FFF4E0;text-align:center}
.man-kicker{margin:0;font-size:30px;color:#15B8A6}
.man-line{margin:6px 0 0;font:800 clamp(40px,8vw,96px)/1 var(--f-d);letter-spacing:-.04em;color:#FF7AB6;text-shadow:0 0 40px rgba(255,122,182,.35)}
.man-sub{max-width:60ch;margin:14px auto 0;color:#CFC3E0}
.reels{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;max-width:760px}
.reel{margin:0}.reel img{width:100%;height:auto;border-radius:16px;display:block;box-shadow:0 12px 30px rgba(29,20,51,.25)}
.reel figcaption{margin-top:6px;font:500 12px ui-monospace,monospace;color:var(--ink-2);overflow-wrap:anywhere}
.logos{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.lg{display:grid;place-items:center;padding:30px 24px;border-radius:26px 14px 30px 18px;min-height:150px}
.lg-svg{width:100%;max-width:380px;height:auto}
.lg-svg--stack{max-width:220px}
.lg--paper{background:#FFF4E0;border:2px solid var(--line)}.lg--night{background:#1D1433}.lg--jac{background:#7A4FD8}.lg--stack{background:#FFC629}
.rules{margin:18px 0 0;padding-left:20px;display:grid;gap:6px;max-width:70ch}

.swatches{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.sw{display:flex;flex-direction:column;gap:8px}
.chip{display:flex;flex-direction:column;justify-content:flex-end;gap:2px;min-height:118px;padding:12px 14px;background:var(--c);color:var(--t);border-radius:40% 60% 45% 55% / 30% 40% 60% 70%}
.sw:nth-child(even) .chip{border-radius:55% 45% 60% 40% / 45% 60% 40% 55%}
.chip b{font:800 15px var(--f-d)}
.chip code{background:none;padding:0;color:inherit;font-size:12px}
.sw-txt{font-size:13.5px;line-height:1.4;color:var(--ink-2)}
.sw:last-child .chip{box-shadow:inset 0 0 0 2px var(--line)}

.types{display:grid;gap:14px}
.ty{padding:22px 24px;border-radius:24px;background:var(--card);border:2px solid var(--line)}
.lbl{font:700 12px var(--f-b);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2)}
.ty p{margin:8px 0}
.ty small{color:var(--ink-2);font-size:14px}
.ty-d{font:800 clamp(34px,6vw,64px)/1 var(--f-d);letter-spacing:-.04em}
.ty-b{font:600 22px/1.4 var(--f-b);max-width:40ch}
.ty-h{font:700 clamp(34px,5vw,54px)/1 var(--f-h);color:var(--shuka)}

.devs{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.dev{margin:0}
.shape{width:100%;height:auto;display:block;border-radius:20px;background:var(--card);border:2px solid var(--line)}
.dev--night .shape{border-color:#35294F}
.dev figcaption{margin-top:6px;font-size:13px;color:var(--ink-2)}

.series{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.series-row{display:grid;grid-template-columns:110px 1fr 110px;gap:18px;align-items:center;padding:12px 14px;border-radius:22px;background:var(--card);border:2px solid var(--line)}
.when{font:800 13px/1.3 var(--f-d);color:var(--accent-ink)}
.series-row h3{margin:0;font:800 18px/1.2 var(--f-d);letter-spacing:-.02em}
.series-row p{margin:4px 0 0;font-size:15px;color:var(--ink-2)}
.series-row img{width:110px;height:auto;border-radius:10px;display:block}

.lanes{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.lane{padding:16px;border-radius:26px 16px 28px 14px;background:var(--c);color:var(--t);display:flex;flex-direction:column;gap:6px}
.lane b{font:800 18px var(--f-d)}
.lane span{font-weight:700;font-size:14.5px;line-height:1.35}
.lane small{font-size:13px;line-height:1.4;opacity:.9}
.reach{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.reach li{padding:14px 16px;border-radius:18px;border:2px dashed var(--line);display:flex;flex-direction:column;gap:4px}
.reach b{font:800 15px var(--f-d)}
.reach span{font-size:14px;color:var(--ink-2)}

.hooks{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,1fr);gap:12px;counter-reset:h}
.hooks li{counter-increment:h;position:relative;padding:18px 18px 18px 60px;border-radius:24px;background:var(--card);border:2px solid var(--line);display:flex;flex-direction:column;gap:4px}
.hooks li::before{content:counter(h);position:absolute;left:14px;top:14px;width:34px;height:32px;display:grid;place-items:center;background:var(--jua);color:#1D1433;font:800 15px var(--f-d);border-radius:55% 45% 60% 40%}
.hooks b{font:800 17px var(--f-d)}
.hooks span{font-size:15px;color:var(--ink-2)}

.glossary{margin:0;display:grid;grid-template-columns:1fr 1fr;gap:0 28px}
.gl{display:grid;grid-template-columns:170px 1fr;gap:14px;padding:12px 0;border-bottom:2px dotted var(--line)}
.gl dt{font:800 17px/1.2 var(--f-d)}
.gl dt small{display:block;margin-top:4px;font:600 12px var(--f-b);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2)}
.gl dd{margin:0;font-size:15px;color:var(--ink-2)}
.doit{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:24px}
.doit>div{padding:18px 22px;border-radius:26px 14px 28px 16px}
.doit .hand{font-size:30px}
.doit p{margin:4px 0 0}
.yes{background:#0E7C50;color:#fff}.no{background:#D4301F;color:#fff}

.gallery{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;align-items:start}
.g-item{margin:0}
.g-item img{width:100%;height:auto;display:block;border-radius:12px}
.g-item figcaption{margin-top:4px;font:500 12px ui-monospace,monospace;color:var(--ink-2);overflow-wrap:anywhere}
.profiles{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start}
.pf{margin:0}.pf img{width:100%;height:auto;display:block;border-radius:12px}
.pf--wide{grid-column:1/-1}
.pf--av img{width:150px;border-radius:50%}
.pf figcaption{margin-top:4px;font-size:13px;color:var(--ink-2)}
.handles{margin-top:18px;padding:12px 16px;border-radius:16px;background:var(--paper-2)}

.sec--night{margin-inline:calc(-1*clamp(16px,4vw,48px));padding-inline:clamp(16px,4vw,48px);background:#1D1433;color:#FFF4E0;border-top:none;border-radius:40px 60px 30px 70px/30px 40px 30px 40px}
.sec--night .note{color:#CFC3E0}
.flow{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
.flow li{position:relative;padding:16px 14px;border:2px solid #15B8A6;border-radius:20px;display:flex;flex-direction:column;gap:6px;background:#2A1F45}
.flow li:nth-child(5){border-color:#FFC629;background:#3A2A12}
.flow b{font:800 16px var(--f-d);color:#FFC629}
.flow li:nth-child(5) b{color:#FFC629}
.flow span{font-size:13.5px;line-height:1.4;color:#E9E1F5}
.f-when{min-height:1.2em;font:700 11px var(--f-b)!important;letter-spacing:.08em;text-transform:uppercase;color:#15B8A6!important}

.moneys{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
.money{padding:16px;border-radius:24px 14px 26px 16px;background:var(--card);border:2px solid var(--line);display:flex;flex-direction:column;gap:6px}
.m-tag{align-self:flex-start;padding:3px 10px;border-radius:999px;background:var(--chai);color:#fff;font:700 11.5px var(--f-b);letter-spacing:.04em}
.money h3{margin:0;font:800 17px var(--f-d)}
.money p{margin:0;font-size:14px;color:var(--ink-2)}
.plan90{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.plan90 li{padding:16px;border-top:6px solid var(--jua);background:var(--card);border-radius:4px 4px 20px 20px}
.plan90 p{margin:6px 0 0;font-size:14.5px;color:var(--ink-2)}

.foot{max-width:1120px;margin:40px auto 0;padding-block:28px 40px;border-top:2px dashed var(--line);display:flex;align-items:center;gap:16px;font-size:14px;color:var(--ink-2)}
.m--foot{width:70px;flex:none}

@media (max-width:980px){.play{grid-template-columns:repeat(2,1fr)}.lore{grid-template-columns:repeat(2,1fr)}.cast-row,.pose-row{grid-template-columns:repeat(4,1fr)}.exprs{grid-template-columns:repeat(4,1fr)}.swatches{grid-template-columns:repeat(3,1fr)}.lanes,.reach,.moneys{grid-template-columns:repeat(2,1fr)}.flow{grid-template-columns:repeat(2,1fr)}.plan90,.pillars,.devs{grid-template-columns:repeat(2,1fr)}.hooks{grid-template-columns:repeat(2,1fr)}.gallery{grid-template-columns:repeat(3,1fr)}.glossary{grid-template-columns:1fr}}
@media (max-width:620px){.reels{grid-template-columns:repeat(2,1fr)}.play,.lore{grid-template-columns:1fr}.stickers img{width:72px;height:72px}.cast-row,.pose-row{grid-template-columns:repeat(2,1fr)}.comic-demo{grid-template-columns:1fr}.hero{grid-template-columns:1fr}.hero-art{order:-1}.m--hero{max-width:200px}.modes,.logos,.doit,.profiles{grid-template-columns:1fr}.exprs{grid-template-columns:repeat(2,1fr)}.swatches{grid-template-columns:repeat(2,1fr)}.lanes,.reach,.moneys,.flow,.plan90,.pillars,.hooks,.devs{grid-template-columns:1fr}.gallery{grid-template-columns:repeat(2,1fr)}.series-row{grid-template-columns:1fr 84px}.series-row .when{grid-column:1/-1}.series-row img{width:84px}.gl{grid-template-columns:1fr;gap:4px}}
"""

FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Caveat:wght@700&family=Figtree:wght@400;500;600;700;800&family=Unbounded:wght@700;800&display=swap">'


def main() -> None:
    body = build_body()
    head = f"<title>Jua Kesho</title>\n{FONTS}\n<style>{CSS}</style>"
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
