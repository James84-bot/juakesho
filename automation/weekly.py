"""
weekly.py — "Kenya This Week", the weekly long-form YouTube show (8-12 minutes, 16:9), narrated by the owner.

YouTube does not pay channels whose videos are template slideshows or read out other people's news (its
"inauthentic content" policy, July 2025). Long-form watch hours are also the faster road to the Partner Program.
So once a week the channel gets something no template makes: the week's biggest stories, explained in a human
voice, with chapters.

    Saturday 09:00   pick the week's 6 biggest stories (our own published posts: already sourced and checked),
                     write the script (only facts those posts state), send it to Telegram one part per message
    you              reply to each part with a voice note (re-record a part by replying again: the last one counts)
    tick             each voice note is filed under its part; when every part has one, the build is queued
    weeklywork       photos, 16:9 plates with a slow camera, titles, chapters, thumbnail; uploaded to YouTube for
                     Sunday 18:00 EAT (straight away if that time has passed)

State: state/weekly/<week>.json. Nothing here invents a fact: a number in the script that is not in its story's
post fails the check and the script is written again (twice at most), or the week is skipped.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import brands

DIR = brands.STATE / "weekly"
STORIES = 6
WORDS = {"intro": (40, 110), "story": (140, 260), "outro": (35, 90)}   # spoken: about 150 words a minute
PUBLISH = (6, 18, 0)   # Sunday 18:00 EAT (weekday 6 = Sunday)
SHOW = "Kenya This Week"
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def path(label: str) -> Path:
    return DIR / f"{label}.json"


def load(label: str) -> dict:
    try:
        return json.loads(path(label).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(label: str, state: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    path(label).write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# The week's stories
# ---------------------------------------------------------------------------
def candidates(weeks: list[dict], since: dt.datetime, until: dt.datetime) -> list[dict]:
    """Our posts that went out between `since` and `until` and carry a script (beats): one story each."""
    out = []
    for data in weeks:
        for p in data.get("posts", []):
            if p.get("status") != "published" or not p.get("beats") or p.get("n") or p.get("template") == "tazama":
                continue
            try:
                at = dt.datetime.fromisoformat(p.get("published_at") or p["publish_at"])
            except (KeyError, ValueError):
                continue
            if since <= at <= until:
                out.append({**p, "_label": data.get("collection", "")})
    return out


def pick(posts: list[dict], learned: dict, n: int = STORIES) -> list[dict]:
    """The stories people watched most (YouTube views plus Instagram reach), different stories only, in the order
    they happened. A post with no numbers yet counts by its editor's score."""
    yt = {r["id"]: r.get("views", 0) for r in learned.get("youtube") or []}
    ig = {r["id"]: r.get("reach", 0) for r in learned.get("all") or []}

    def weight(p: dict) -> float:
        seen = yt.get(p["id"], 0) + ig.get(p["id"], 0)
        return seen if seen else ((p.get("critic") or {}).get("avg") or 0) * 10

    import guard
    chosen: list[dict] = []
    for p in sorted(posts, key=weight, reverse=True):
        words = guard._stems(" ".join(p.get("beats") or []))
        if any(len(words & guard._stems(" ".join(q.get("beats") or []))) >= 4 for q in chosen):
            continue   # the same story told twice this week
        chosen.append(p)
        if len(chosen) >= n:
            break
    return sorted(chosen, key=lambda p: p.get("published_at") or p.get("publish_at", ""))


def facts_of(post: dict) -> str:
    """Everything a post states, the only material its part of the script may use."""
    keys = ("line", "fact", "message", "impact", "action", "who", "where", "when", "caption")
    parts = [str(post.get(k) or "") for k in keys] + [str(b).replace("*", "") for b in post.get("beats") or []]
    parts += [f"{x.get('outlet', '')}: {x.get('title', '')}" for x in post.get("source_links") or []]
    return "\n".join(x for x in parts if x.strip())


# ---------------------------------------------------------------------------
# The script
# ---------------------------------------------------------------------------
RULES = f"""You write the script of "{SHOW}", a weekly YouTube show by Kenya on Record, read aloud by one Kenyan
narrator. It explains the week's biggest Kenyan stories to informed Kenyans: what happened, what the record shows,
what it means for ordinary Kenyans, and what to watch next. Fair to every side, never an insult, no slogans.

HARD RULES
- Use ONLY the facts given for each story. Every number, name, date and claim must already be in that story's
  material. If it isn't there, leave it out. No background "everyone knows" facts, no predictions as facts.
- An accusation is the accuser's claim, never ours: say who says it.
- Spoken Kenyan English: short sentences, contractions, plain words, the way a sharp friend explains the news.
  Numbers written as people say them in Kenya ("Sh47 billion", "13 years"). No lists, no headings inside a part.
- Never: em dashes, "it's not just X, it's Y", "in today's world", "delve", "navigate", "landscape", "unlock",
  "pivotal", "crucial", "harness", "foster", "here's the thing", "let's dive in", "buckle up", "stay tuned".
- No numbering of stories in the voice ("story number one"): move between stories with a natural line.
- Written to be read aloud: sentences of 8-20 words, one idea each. Dates as people say them ("on Monday",
  "on 2 November"), never "the second of November 2026".
- Vary the endings. Say "demand" at most twice in the whole script; never end two parts with the same kind of
  line ("the big question", "what remains to be seen"). Swahili words at most once in the whole script.

SHAPE
- intro: {WORDS['intro'][0]}-{WORDS['intro'][1]} words. Open on the most striking fact of the week (from the stories),
  then say in one line what the show covers. Do not greet with "hello guys".
- one part per story, {WORDS['story'][0]}-{WORDS['story'][1]} words each, in the order given: what happened (who, where,
  when), the detail that matters, what it means for ordinary Kenyans, then the next step or the question it leaves.
- outro: {WORDS['outro'][0]}-{WORDS['outro'][1]} words: the one question for the comments, then ask viewers to subscribe for
  next week's show. No goodbye clichés.

Return ONLY JSON:
{{"title": "YouTube title, max 90 characters, the biggest story first, then 'and more' or the week's theme",
 "thumbnail": "2 to 4 words for the thumbnail, the hook of the biggest story",
 "summary": "two plain sentences for the top of the description",
 "intro": "...",
 "stories": [{{"id": "the story id", "chapter": "chapter title, max 45 characters", "script": "..."}}],
 "outro": "..."}}"""


def prompt(posts: list[dict], week_name: str) -> str:
    blocks = [f"STORY {p['id']} (published {str(p.get('published_at') or p['publish_at'])[:10]})\n{facts_of(p)}"
              for p in posts]
    return f"The week: {week_name}.\n\n" + "\n\n".join(blocks)


def numbers(text: str) -> set[str]:
    """The figures in a text, written one way ("07" and "7" are the same day, "1,200" and "1200" the same sum)."""
    out = set()
    for m in NUM.findall(str(text)):
        n = re.sub(r",", "", m).rstrip(".")
        out.add(n.lstrip("0") or "0" if "." not in n else n)
    return out


def check(script: dict, posts: list[dict], extra: str = "") -> list[str]:
    """What is wrong with a script: a missing story, a part too short or long, a banned phrase, or a number its
    story's material does not contain."""
    import guard
    problems = []
    by_id = {p["id"]: p for p in posts}
    stories = script.get("stories") or []
    if [s.get("id") for s in stories] != [p["id"] for p in posts]:
        problems.append("the stories must be exactly the given ids, in the given order")
    every = numbers("\n".join(facts_of(p) for p in posts) + "\n" + extra)   # extra: the week's dates
    for key, (lo, hi) in (("intro", WORDS["intro"]), ("outro", WORDS["outro"])):
        n = len(str(script.get(key) or "").split())
        if not lo <= n <= hi + 30:
            problems.append(f"{key} is {n} words (wanted {lo}-{hi})")
        extra = numbers(script.get(key) or "") - every
        if extra:
            problems.append(f"{key}: numbers not in any story: {', '.join(sorted(extra))}")
    for s in stories:
        text, post = str(s.get("script") or ""), by_id.get(s.get("id"))
        n = len(text.split())
        if not WORDS["story"][0] <= n <= WORDS["story"][1] + 40:
            problems.append(f"{s.get('id')}: {n} words (wanted {WORDS['story'][0]}-{WORDS['story'][1]})")
        if post is not None:
            extra = numbers(text) - numbers(facts_of(post))
            if extra:
                problems.append(f"{s.get('id')}: numbers not in its story: {', '.join(sorted(extra))}")
        if not str(s.get("chapter") or "").strip() or len(str(s.get("chapter"))) > 60:
            problems.append(f"{s.get('id')}: chapter title missing or too long")
    allt = " ".join([str(script.get("intro") or ""), str(script.get("outro") or "")] + [str(s.get("script") or "") for s in stories])
    if len(re.findall(r"\bdemand", allt, re.I)) > 2:
        problems.append("'demand' is said more than twice: vary it")
    long = [x.strip()[:60] for x in re.split(r"(?<=[.!?])\s+", allt) if len(x.split()) > 28]
    if long:
        problems.append(f"{len(long)} sentence(s) over 28 words, too long to read aloud: " + " | ".join(long[:3]))
    bad = [w for w in guard.NEVER_WORDS if re.search(rf"\b{re.escape(w)}\b", allt, re.I)]
    if "—" in allt:
        bad.append("em dash")
    if bad:
        problems.append("banned words: " + ", ".join(sorted(set(bad))))
    if len(str(script.get("title") or "")) > 100 or not script.get("title"):
        problems.append("title missing or over 100 characters")
    return problems


def write(posts: list[dict], week_name: str, ask=None, tries: int = 3) -> tuple[dict | None, list[str]]:
    """The script, checked; (None, problems) when three tries still break a rule."""
    import draft
    ask = ask or (lambda system, user: draft.extract_json(draft.call_claude(system, user, max_tokens=6000)))
    user, problems = prompt(posts, week_name), []
    for _ in range(tries):
        try:
            script = ask(RULES, user + (("\n\nYOUR LAST SCRIPT BROKE THESE RULES, fix them:\n- " + "\n- ".join(problems))
                                         if problems else ""))
        except Exception as e:
            problems = [f"writer failed: {str(e)[:160]}"]
            continue
        problems = check(script, posts, extra=week_name)
        if not problems:
            return script, []
    return None, problems


def parts(script: dict) -> list[dict]:
    """The script as the parts the narrator records, one voice note each."""
    out = [{"key": "intro", "title": "Intro", "text": script["intro"]}]
    out += [{"key": s["id"], "title": s["chapter"], "text": s["script"], "post": s["id"]} for s in script["stories"]]
    out.append({"key": "outro", "title": "Outro", "text": script["outro"]})
    return out


def part_message(i: int, total: int, part: dict) -> str:
    import html
    return (f"🎙 <b>{SHOW}: part {i} of {total}, {html.escape(part['title'])}</b>\n\n{html.escape(part['text'])}\n\n"
            "<i>Reply to THIS message with a voice note reading it. Calm and clear, like telling a friend. "
            "To redo it, just reply again: the last one counts.</i>")


def file_voice(state: dict, reply_to: int, voice: dict) -> dict | None:
    """Files a voice note under the part whose message it replies to. Returns that part, or None."""
    for part in state.get("parts", []):
        if part.get("msg") == reply_to:
            part["voice"] = {"file_id": voice.get("file_id"), "duration": voice.get("duration"),
                             "mime": voice.get("mime_type", "audio/ogg")}
            if all(p.get("voice") for p in state["parts"]) and state.get("status") == "recording":
                state["status"] = "ready"
            return part
    return None


def publish_at(now: dt.datetime) -> dt.datetime | None:
    """This week's Sunday 18:00 EAT, or None when it has passed (then the video goes out at once)."""
    day, hour, minute = PUBLISH
    sunday = (now + dt.timedelta(days=(day - now.weekday()) % 7)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return sunday if sunday > now + dt.timedelta(minutes=20) else None


def chapters(durations: list[tuple[str, float]]) -> str:
    """YouTube chapters: the first at 0:00, each at least 10 seconds."""
    lines, t = [], 0.0
    for title, d in durations:
        m, s = divmod(int(t), 60)
        lines.append(f"{m}:{s:02d} {title}")
        t += d
    return "\n".join(lines)


def description(script: dict, posts: list[dict], chapter_text: str) -> str:
    srcs = []
    for p in posts:
        for x in (p.get("source_links") or [])[:2]:
            if x.get("link"):
                srcs.append(f"• {x.get('outlet', '')}: {x.get('title', '')[:90]} {x['link']}")
    return (f"{script.get('summary', '').strip()}\n\nChapters\n{chapter_text}\n\nSources\n" + "\n".join(srcs[:14])
            + "\n\nEvery story was first posted on Kenya on Record with its sources. Subscribe for next week's show."
            + "\n\n#KenyaOnRecord #KenyaNews #KenyaThisWeek")


# ---------------------------------------------------------------------------
# The video (16:9, 1920x1080, 30 fps): photos on slow camera moves, the chapter's title, the narrator's voice
# ---------------------------------------------------------------------------
W, H, FPS = 1920, 1080, 30
PLATE = (2304, 1296)   # 1.2x the frame: the camera moves inside it without enlarging the photo
GAP = 0.45             # silence between parts
SHOT_S = 9.0           # a new picture about this often
TITLE_S = 3.2          # the chapter title card at the start of each story


def plate(src: Path, out: Path) -> Path:
    """One picture as a 16:9 plate: full-bleed when it is big enough, else whole and sharp over a blurred, darkened
    copy of itself (never blown up more than 1.35x)."""
    from PIL import Image, ImageDraw, ImageFilter
    pw, ph = PLATE
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        cover = max(pw / w, ph / h)
        if cover <= 1.35:
            im = im.resize((round(w * cover), round(h * cover)), Image.LANCZOS)
            x, y = (im.width - pw) // 2, max(0, (im.height - ph) // 3)
            im.crop((x, y, x + pw, y + ph)).save(out, quality=92)
            return out
        bg = im.resize((round(w * cover), round(h * cover)), Image.LANCZOS)
        x, y = (bg.width - pw) // 2, (bg.height - ph) // 2
        bg = bg.crop((x, y, x + pw, y + ph)).filter(ImageFilter.GaussianBlur(36))
        bg = Image.eval(bg, lambda v: int(v * 0.42))
        s = min(pw * 0.86 / w, ph * 0.86 / h, 1.35)
        fg = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
        mask = Image.new("L", fg.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, fg.width - 1, fg.height - 1), radius=22, fill=255)
        bg.paste(fg, ((pw - fg.width) // 2, (ph - fg.height) // 2), mask)
        bg.save(out, quality=92)
    return out


def shots(duration: float, n_pictures: int) -> list[tuple[int, float]]:
    """(picture index, seconds) for one part: a new picture about every SHOT_S seconds, taking turns."""
    k = max(1, round(duration / SHOT_S))
    return [(i % max(1, n_pictures), duration / k) for i in range(k)]


CARD_CSS = """html,body{margin:0;width:1920px;height:1080px;background:transparent;overflow:hidden}
*{box-sizing:border-box} .x{position:absolute;inset:0}
.shade{background:linear-gradient(to top,rgba(14,12,11,.92) 0,rgba(14,12,11,.55) 26%,rgba(14,12,11,0) 48%)}
.full{background:rgba(14,12,11,.72)}
.logo{position:absolute;left:72px;top:56px;height:44px}
.pill{display:inline-block;background:#C4111A;color:#fff;font:800 26px/1 "Inter Tight";letter-spacing:.08em;
 text-transform:uppercase;padding:11px 16px;border-radius:6px}
.low{position:absolute;left:72px;right:420px;bottom:84px}
.low h1{margin:18px 0 0;font:900 64px/1.04 "Inter Tight";letter-spacing:-.02em;color:#fff}
.cr{position:absolute;right:72px;bottom:56px;font:600 22px/1 "Inter";color:rgba(255,255,255,.6)}
.big{position:absolute;left:120px;right:200px;top:50%;transform:translateY(-50%)}
.big h1{margin:26px 0 0;font:900 104px/1.02 "Inter Tight";letter-spacing:-.025em;color:#fff}
.big p{margin:24px 0 0;font:700 36px/1.2 "Inter";color:rgba(255,255,255,.82)}
.thumb h1{font-size:150px;line-height:.98;max-width:1100px}
.thumb .m{background:#C4111A;padding:0 .12em;border-radius:.05em}
"""


def card_html(kind: str, title: str, sub: str = "", credit: str = "", photo: str = "") -> str:
    """The overlays and cards, drawn by the browser (transparent where the video shows through)."""
    import html
    import brandkit
    import render
    fonts = brandkit.font_faces((brands.ROOT / "assets" / "fonts").as_uri())
    logo = (render.LOGO / "wordmark-on-dark.svg").as_uri()
    t, s = html.escape(title), html.escape(sub)
    if kind == "lower":
        body = (f'<div class="x shade"></div><img class="logo" src="{logo}"><div class="low"><span class="pill">{SHOW}</span>'
                f'<h1>{t}</h1></div>' + (f'<div class="cr">{html.escape(credit)}</div>' if credit else ""))
    elif kind == "title":
        body = f'<div class="x full"></div><div class="big"><span class="pill">{SHOW}</span><h1>{t}</h1></div>'
    elif kind == "thumb":
        bg = f'<img src="{photo}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">' if photo else ""
        words = t.split()
        hot = " ".join(words[:-1]) + f' <span class="m">{words[-1]}</span>' if len(words) > 1 else f'<span class="m">{t}</span>'
        body = (f'{bg}<div class="x" style="background:linear-gradient(90deg,rgba(14,12,11,.92) 0,rgba(14,12,11,.6) 55%,'
                f'rgba(14,12,11,.1) 100%)"></div><img class="logo" src="{logo}" style="height:56px">'
                f'<div class="big thumb"><span class="pill">{SHOW}</span><h1>{hot}</h1></div>')
    else:   # "end": the last seconds, where YouTube's end screen sits
        body = (f'<div class="x" style="background:#0E0C0B"></div><img class="logo" src="{logo}" style="height:64px;left:120px;top:120px">'
                f'<div class="big"><span class="pill">{SHOW}</span><h1>{t}</h1><p>{s}</p></div>')
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{fonts}{CARD_CSS}</style></head><body>{body}</body></html>"


def draw(page, html_text: str, out: Path, size: tuple[int, int] = (W, H), jpeg: bool = False) -> Path:
    """The card as a picture. Loaded from a file next to `out` (a page set from a string may not read local fonts
    or the logo)."""
    page.set_viewport_size({"width": size[0], "height": size[1]})
    src = out.with_suffix(".html")
    src.write_text(html_text, encoding="utf-8")
    page.goto(src.as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(250)
    page.screenshot(path=str(out), omit_background=not jpeg, type="jpeg" if jpeg else "png", **({"quality": 90} if jpeg else {}))
    return out


def clean_voice(ff: str, src: Path, out: Path) -> float:
    """A phone voice note made broadcast-clean: rumble cut, light noise reduction, gentle compression, -16 LUFS."""
    import subprocess
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-af",
                    "highpass=f=80,afftdn=nf=-25,acompressor=threshold=-21dB:ratio=3:attack=6:release=90,"
                    "loudnorm=I=-16:TP=-1.5:LRA=7", "-ar", "48000", "-ac", "1", str(out)], check=True)
    return duration(ff, out)


def duration(ff: str, f: Path) -> float:
    import subprocess
    probe = subprocess.run([ff, "-hide_banner", "-i", str(f)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def part_video(ff: str, plates: list[Path], lower: Path, title: Path | None, dur: float, work: Path, key: str) -> Path:
    """One part: its pictures on slow pushes, the lower third throughout, the title card over the first seconds."""
    import subprocess
    clips = []
    for i, (k, secs) in enumerate(shots(dur, len(plates))):
        n = max(1, round(secs * FPS))
        fx, fy = (0.5, 0.42) if i % 2 == 0 else (0.38, 0.5)
        clip = work / f"{key}-{i}.mp4"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(plates[k]), "-vf",
                        f"zoompan=z='1+0.07*on/{n}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d={n}:s={W}x{H}:fps={FPS},"
                        "format=yuv420p", "-frames:v", str(n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        str(clip)], check=True)
        clips.append(clip)
    lst = work / f"{key}-list.txt"
    lst.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    base = work / f"{key}-base.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)], check=True)
    out = work / f"{key}.mp4"
    if title is not None:
        graph = (f"[0][1]overlay=0:0[a];[2]format=rgba,fade=t=out:st={TITLE_S - 0.5}:d=0.5:alpha=1[t];"
                 f"[a][t]overlay=0:0:enable='lte(t,{TITLE_S})'[v]")
        inputs = ["-i", str(base), "-i", str(lower), "-loop", "1", "-t", str(TITLE_S), "-i", str(title)]
    else:
        graph, inputs = "[0][1]overlay=0:0[v]", ["-i", str(base), "-i", str(lower)]
    subprocess.run([ff, "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[v]", "-t", f"{dur:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
                   check=True)
    return out


def still_video(ff: str, image: Path, dur: float, out: Path) -> Path:
    import subprocess
    subprocess.run([ff, "-y", "-loglevel", "error", "-loop", "1", "-t", f"{dur:.3f}", "-i", str(image), "-vf",
                    f"scale={W}:{H},format=yuv420p", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    str(out)], check=True)
    return out


def mix_audio(ff: str, voices: list[tuple[Path, float]], total: float, out: Path, music: Path | None,
              end_len: float | None = None) -> Path:
    """The narration, part after part with a short gap, a whoosh where each part starts, music under the intro and
    the end card only; the whole programme at -14 LUFS (YouTube's loudness)."""
    import subprocess
    import numpy as np
    import sound
    sr = 48000
    track = np.zeros(int(sr * (total + 1)), dtype=np.float32)
    t = 0.0
    for i, (wav, d) in enumerate(voices):
        import wave
        with wave.open(str(wav), "rb") as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        start = int(sr * t)
        track[start:start + len(data)] += data[: len(track) - start]
        if i:   # a soft whoosh into each new part (sound.py works at its own rate: resample by index)
            wh = sound.whoosh(0.34, seed=i) * 0.25
            idx = np.linspace(0, len(wh) - 1, int(len(wh) * sr / sound.SR)).astype(int)
            s0 = max(0, start - int(sr * 0.2))
            track[s0:s0 + len(idx)] += wh[idx][: len(track) - s0]
        t += d + GAP
    raw = out.with_name("voice-mix.wav")
    sound_write(track, raw, sr)
    if music is None:
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1.5:LRA=9",
                        "-ar", "48000", "-ac", "2", "-t", f"{total:.3f}", str(out)], check=True)
        return out
    intro_end, end_start = voices[0][1] + GAP, total - (end_len or voices[-1][1] + GAP)
    vol = (f"volume='if(lt(t,{intro_end:.2f}),0.16,if(gt(t,{end_start:.2f}),0.16,0))':eval=frame")
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-stream_loop", "-1", "-i", str(music),
                    "-filter_complex", f"[1]{vol},afade=t=out:st={max(0.0, total - 2):.2f}:d=2[m];"
                    f"[0][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[a]",
                    "-map", "[a]", "-ar", "48000", "-ac", "2", "-t", f"{total:.3f}", str(out)], check=True)
    return out


def sound_write(samples, path: Path, sr: int) -> None:
    import wave
    import numpy as np
    peak = float(np.max(np.abs(samples))) or 1.0
    data = (np.clip(samples / max(peak, 1.0), -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


def build(state: dict, posts: dict[str, dict], audio: dict[str, Path], out_dir: Path) -> dict:
    """The finished show: {"video", "thumbnail", "chapters", "durations"}. `audio`: each part's voice file."""
    import shutil
    import subprocess
    import tempfile
    from playwright.sync_api import sync_playwright
    import photos as photolib
    import video as videolib
    ff = videolib.ffmpeg_bin()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="weekly-"))
    parts_ = state["parts"]
    # the voice of every part, cleaned, and its length
    voices = [(work / f"v-{i}.wav", 0.0) for i in range(len(parts_))]
    voices = [(w, clean_voice(ff, audio[p["key"]], w)) for (w, _), p in zip(voices, parts_)]
    # each story's pictures (the same search its post used)
    pics: dict[str, list[dict]] = {}
    for p in parts_:
        post = posts.get(p.get("post") or "")
        if not post:
            continue
        copy = {k: v for k, v in post.items() if k not in {"photo_file", "extra_photos", "shot_info", "person_file"}}
        try:
            photolib.attach([copy], work / "photos")
        except Exception as e:
            print(f"  photos for {p['key']} failed: {e}")
        files = [copy.get("photo_file")] + list(copy.get("extra_photos") or [])
        info = copy.get("shot_info") or [{"credit": copy.get("photo_credit", "")}]
        pics[p["key"]] = [{"file": Path(f), "credit": (info[i] if i < len(info) else {}).get("credit", "")}
                          for i, f in enumerate(files) if f and Path(f).is_file()]
    lead = next((x for p in parts_ for x in pics.get(p["key"], [])), None)
    made, chapters_in = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for i, (p, (wav, d)) in enumerate(zip(parts_, voices)):
            dur = d + GAP
            key = re.sub(r"\W", "", p["key"])[-24:] or f"p{i}"
            if p["key"] == "intro":
                title = state.get("week_name", "")
                bg = plate(lead["file"], work / "intro-plate.jpg") if lead else None
                card = draw(page, card_html("title", SHOW, title), work / "intro-card.png")
                made.append(part_video(ff, [bg], card, None, dur, work, key) if bg else still_video(ff, card, dur, work / f"{key}.mp4"))
            elif p["key"] == "outro":
                end = draw(page, card_html("end", "Subscribe for next week's show", "@kenyaonrecord · Kenya on Record"),
                           work / "end.jpg", jpeg=True)
                made.append(still_video(ff, end, max(dur, 12.0), work / f"{key}.mp4"))
                dur = max(dur, 12.0)
            else:
                pl = [plate(x["file"], work / f"{key}-plate-{j}.jpg") for j, x in enumerate(pics.get(p["key"], []))]
                credit = " · ".join(dict.fromkeys(x["credit"] for x in pics.get(p["key"], []) if x["credit"]))
                lower = draw(page, card_html("lower", p["title"], credit=credit), work / f"{key}-lower.png")
                title = draw(page, card_html("title", p["title"]), work / f"{key}-title.png")
                if not pl:   # no picture of this story: its title card carries the part
                    made.append(still_video(ff, draw(page, card_html("end", p["title"]), work / f"{key}-alone.jpg", jpeg=True),
                                            dur, work / f"{key}.mp4"))
                else:
                    made.append(part_video(ff, pl, lower, title, dur, work, key))
            chapters_in.append((p["title"], dur))
        thumb = draw(page, card_html("thumb", state.get("script", {}).get("thumbnail") or SHOW,
                                     photo=lead["file"].resolve().as_uri() if lead else ""),
                     out_dir / f"{state['label']}-thumbnail.jpg", size=(1280, 720), jpeg=True)
        browser.close()
    total = sum(d for _, d in chapters_in)
    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{m.as_posix()}'\n" for m in made), encoding="utf-8")
    picture = work / "picture.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(picture)], check=True)
    lib = videolib._library()
    music = next((t["path"] for t in lib if t.get("mood") == "uplifting"), None) or (lib[0]["path"] if lib else None)
    sound_track = mix_audio(ff, [(w, d) for w, d in voices], total, work / "sound.wav", music, end_len=chapters_in[-1][1])
    final = out_dir / f"{state['label']}-kenya-this-week.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(picture), "-i", str(sound_track), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(final)], check=True)
    shutil.rmtree(work, ignore_errors=True)
    return {"video": str(final), "thumbnail": str(thumb), "chapters": chapters(chapters_in), "seconds": round(total, 1)}
