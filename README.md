# Jua Kesho

*Jua nchi yako* (know your country). An independent, faceless, non-partisan Kenyan channel for 18–30s: the general
knowledge every Kenyan should have, politics with receipts (Promise Tracker, Set It Straight, Follow the Money),
scams and the future. Kenyan flag colours, real photos, bold type, sourced facts.
**jua** = the sun + to know · **kesho** = tomorrow.

**Live:** brand book at <https://james84-bot.github.io/juakesho/brand-book/> · repo <https://github.com/James84-bot/juakesho>

```
brand-book/index.html        The brand book (open in a browser)
assets/logo/                 Sunrise mark, wordmark, stacked logo, icons (outlined SVG, no fonts needed)
assets/fonts/                Inter Tight (headlines), Inter (text) (OFL)
exports/posts/               Launch set: 20 designs, PNG + JPEG
exports/reels/               The same set as 9:16 Reels/TikToks (MP4 + cover)
exports/profiles/            Avatars, YouTube / X / Facebook banners
automation/                  The self-running content engine
  brand.json                 Name, handle, colours (4 families × 11 shades): change here, everything follows
  palette.py                 Builds the flag-colour shade ramps (ink, red, green) in OKLCH and checks contrast
  brandkit.py                Brand constants, fonts (plus legacy drawing helpers, out of rotation)
  templates/*.html.j2        One editorial template per series (base.html.j2: grid, type, photo, motion, auto-fit)
  content/posts.json         Launch posts (edit or add, then render)
  calendar.json              Weekly rhythm, audience lanes, channels
  content/nicknames.json     Names Kenyans use for leaders, and how we may use each (the checker enforces it)
  content/remember.json      Anniversaries (Hatutasahau): the planner schedules them automatically
  state/evidence.jsonl       Every published post with its exact text and sources (the defence file)
  render.py                  posts.json → PNG: photo layout, auto-fit, adaptive ink, visual QA
                             (overflow, collisions, off-canvas, contrast of every text line)
  textfit.py                 Measures text with the real font files (headline sizing)
  photos.py                  Real photos: Pexels scenes, your own photos, licensed photos of real people
  video.py                   posts → 9:16 MP4 Reels (motion, safe zones, deterministic frames)
  sound.py                   The Jua chime + original kalimba and benga-guitar beat (synthesised)
  content/music/             Tracks by artists who gave permission (see README there)
  content/people/            Photos of people (celebrated or on the public record), with rights
  guard.py                   Clean + brand + length + source checks; no name-calling or campaigning
  draft.py                   AI writer (free GitHub Models; Claude optional): trend playbook, civic rules, self-repair
                             + the critic: scores every post (incl. picture + clarity), rewrites under 7.5
                             + a weekly budget cap on AI spend (JUA_WEEKLY_BUDGET_USD, default $0.50)
  trends.py                  Daily Google Trends (KE, NG, ZA, US), politics/tragedy/betting filtered out
  pipeline.py                plan → draft → guard → render → Telegram approval → publish → learn
  tests/                     62 tests, no network needed (the visual QA test uses Chromium if installed)
.github/workflows/autopilot.yml   Runs everything in the cloud, free
```

## Make designs by hand

```bash
cd automation
pip install -r requirements.txt && python -m playwright install chromium
python guard.py content/posts.json         # check first
python render.py --sheet                   # → exports/posts/ + contact sheet
```

## Switch on the autopilot (about 1 hour, once)

1. **Handles:** claim `@juakesho` on Instagram, TikTok, Facebook, YouTube, X and a WhatsApp Channel. Upload the profile images from `exports/profiles/`.
2. **Repo + Pages:** push this folder to a public GitHub repository, then Settings → Pages → Deploy from branch → `main` / root.
   Instagram fetches images and videos from the Pages URL (the publisher checks content types before every post).
3. **Telegram:** create a bot with @BotFather, message it once, then read your chat id from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
4. **Meta:** switch Instagram to a Business/Creator account linked to your Facebook Page. Create a Meta app and get a
   long-lived **Page access token** with `instagram_content_publish`, `pages_manage_posts`, `pages_read_engagement`.
   Note your Page id and Instagram user id.
5. **AI writer: free.** Nothing to do: GitHub Models writes the drafts through the workflow's own token.
   Optional upgrade (paid, best Kenyan voice): repo variable `JUA_PROVIDER=anthropic` + secret `ANTHROPIC_API_KEY`.
   **Recommended (free):** a Pexels key (pexels.com/api) as secret `PEXELS_API_KEY`. The design is photo-led;
   without it, posts fall back to type-only layouts.
6. **Secrets:** in GitHub → Settings → Secrets and variables → Actions, add everything in `automation/.env.example`.
7. **Test:** Actions → autopilot → Run workflow with `rehearse` first (no keys needed; download the
   `rehearsal-week` artifact to see a full mock week). Then run `week`. Previews arrive on Telegram; tap ✅ or ❌.

From then on: every Sunday at 17:00 EAT the next week is drafted, checked, designed and sent to you.
Approved posts publish at their scheduled time. Your job is about 15 minutes of taps a week, plus
forwarding the approved image to the WhatsApp Channel (it has no posting API).

## Useful commands

```bash
python pipeline.py week --mock --dry-run   # full rehearsal, no AI, no posting
python pipeline.py status                  # where every post is
python pipeline.py tick --dry-run          # what would publish now
python pipeline.py redo                    # re-draft posts the checks held back (also in Actions → Run workflow)
python -m unittest discover -s tests -v    # run the tests
python trends.py                           # what Kenya is searching now (safe topics only)
python video.py --only 01-hack-lecture-notes   # render one Reel (~1-2 min; set JUA_VIDEO_WORKERS for more cores)
python palette.py && python build_logo.py && python build_book.py   # rebuild colours, logo files and brand book
```

## Before launch

- [ ] Read every launch post out loud: does it sound like your group chat? You know this audience best.
- [ ] Open each `source` in `content/posts.json` and confirm it (especially the Safaricom scam guidance link).
- [ ] Search the Kenya Industrial Property Institute (KIPI) register for "Jua Kesho" before investing in print or merchandise.
- [ ] Posts that name a public office holder: check every fact against its source before you tap ✅. For a
      high-stakes post, ask a media lawyer first.
- [ ] Rotate tokens if they're ever pasted anywhere public. Never commit `.env`.
