# Jua Kesho

*Kesho iko hapa.* A faceless Kenyan content brand for young, social-native people who haven't yet
tapped into AI and the future. Not a school: hacks, takes, comics and drops, in Kenyan English.
**jua** = the sun + to know · **kesho** = tomorrow.

**Live:** brand book at <https://james84-bot.github.io/juakesho/brand-book/> · repo <https://github.com/James84-bot/juakesho>

```
brand-book/index.html        The brand book (open in a browser)
assets/logo/                 Wordmark, stacked logo, icons (outlined SVG, no fonts needed)
assets/fonts/                Unbounded, Figtree, Caveat (OFL)
exports/posts/               Launch set: 18 designs, PNG + JPEG
exports/reels/               The same 18 as 9:16 Reels/TikToks (MP4 + cover)
exports/stickers/            12-sticker WhatsApp pack (512×512 WebP) + tray icon
exports/profiles/            Avatars, YouTube / X / Facebook banners
automation/                  The self-running content engine
  brand.json                 Name, handle, colours: change here, everything follows
  brandkit.py                Shapes, Glass mode aurora, Kesho Mode, the Jua mascot, the stick cast
  templates/*.html.j2        One template per series
  content/posts.json         Launch posts (edit or add, then render)
  calendar.json              Weekly rhythm, audience lanes, channels
  render.py                  posts.json → PNG, with automatic visual QA (overflow, collisions, off-canvas)
  video.py                   posts → 9:16 MP4 Reels (motion, safe zones, deterministic frames)
  sound.py                   The Jua chime + original kalimba beat (synthesised, license-free)
  guard.py                   Clean-for-everyone + brand + length + source checks
  draft.py                   AI writer (Anthropic API): trend playbook, lore, civic rules, self-repair
                             + the critic: scores every post, rewrites anything under 7.5
  trends.py                  Daily Google Trends (KE, NG, ZA, US), politics/tragedy/betting filtered out
  stickers.py                Builds the WhatsApp sticker pack
  pipeline.py                plan → draft → guard → render → Telegram approval → publish → learn
  tests/                     22 tests, no network needed (the visual QA test uses Chromium if installed)
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
5. **Anthropic:** create an API key at console.anthropic.com.
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
python -m unittest discover -s tests -v    # run the tests
python trends.py                           # what Kenya is searching now (safe topics only)
python stickers.py                         # rebuild the sticker pack
python video.py --only 01-hack-lecture-notes   # render one Reel (~1-2 min; set JUA_VIDEO_WORKERS for more cores)
python build_logo.py && python build_book.py   # rebuild logo files and brand book after brand.json changes
```

## Before launch

- [ ] Read every launch post out loud: does it sound like your group chat? You know this audience best.
- [ ] Import the sticker pack with a sticker-maker app and send it to 10 friends before launch day.
- [ ] Open each `source` in `content/posts.json` and confirm it (especially the Safaricom scam guidance link).
- [ ] Search the Kenya Industrial Property Institute (KIPI) register for "Jua Kesho" before investing in print or merchandise.
- [ ] Rotate tokens if they're ever pasted anywhere public. Never commit `.env`.
