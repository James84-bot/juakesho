# Kenyans Are Asking

The ordinary Kenyan, asking with receipts. An independent, faceless channel that asks the people in power what every Kenyan is already asking: promises against
records, Set It Straight, Follow the Money, scam alerts, and the stories Kenya is talking about this week, in plain
Kenyan English with real photos and sources. Not with any government or party; every side held to the same standard.
Handle **@kenyansareasking** · hashtag **#KenyansAreAsking**.

**Live:** brand book <https://james84-bot.github.io/juakesho/brand-book/> · repo <https://github.com/James84-bot/juakesho>

## How it runs

```
GitHub Actions (free, in the cloud)
  Listener (always on)  answers your taps in seconds, starts the run that saves them, and starts publishing
                        the moment an approved post is due (listener.yml, restarts itself every ~6 hours)
  Sunday 17:00 EAT      plan next week → research → draft → check → editor scores → design → Reels → Telegram
  Daily 09:05 EAT       trend radar to Telegram + one hot post on the day's biggest story
  Backup schedule       autopilot's own cron repeats the above if the listener is ever down
You (Telegram)          ✅ approve · ❌ reject · 🎵 post it yourself · reply/hide comments · send clips
```

Nothing is published, replied to or hidden without your tap. Every post that goes out is also put on the
Instagram Story automatically (the same content you approved), so followers see it in their top row.
Polls ("Your Say", Thursday and Sunday) go out as Reels: people vote A or B in the comments. A card you don't tap expires two hours after its
slot (you get one note); you never have to reject old cards.

### What the writer knows before it writes
- **What Kenya is on** (`demand.py`): stories ranked by outlets carrying them + live X trends + Kenyan TV clips
  (views per hour) + Google searches. Most posts are built on the top five.
- **Live radar** (`radar.py`, no keys): X Kenya trends (trends24) and the most-watched Citizen / NTV / KTN clips.
- **Headlines** (`news.py`) and **search trends** (`trends.py`), every claim traced to a link.

### What keeps it strong
- **Checks** (`guard.py`): length, sources, no name-calling, no tribe, no violence, no em dashes, no AI-sounding
  words, no Swahili filler slang, no shouting (capitals, "!!", BREAKING, 🚨), no politician PR or insult hashtags.
- **Editor** (`draft.py` critic): scores hook, send, clarity, freshness, voice, craft, picture, hold and demand.
  Under 8 gets one rewrite; still under 7 is held back, never sent to you. No two posts on one story.
- **Live hashtags**: matching trending issue hashtags are added to captions automatically. No tag for or
  against any politician or party (no #...Delivers, no #...MustGo, no #Wantam).
- **What it means for you**: every news post says what it changes for an ordinary Kenyan (pocket, services,
  rights, safety, vote), with numbers from the record; the editor scores it, and posts without it are fixed.
- **Photos** (`photos.py`), in this order:
  1. **Your photo of the day**: reply to a post's card with a photo whose caption starts `yangu` (you took it),
     `ruhusa @who (how they agreed)`, or `chanzo @who https://link` (already posted online: credited to whoever
     posted it, used for news and commentary). Agency photos (Getty, AFP, Reuters, AP...) are refused: they bill
     for reuse. The post is redone with the photo and a new card comes back in minutes.
  2. **The event itself, openly licensed**: a photo (CC0 / public domain / CC BY / CC BY-SA, credited) of that story,
     taken in the days around it, found on Wikimedia Commons. The named office holder may be in it; a
     stranger's face may not fill the frame.
  3. **The day's posted photo**: the lead photo of the news report of that story (Kenya News Agency and KBC
     first, then Kenyan outlets: `content/photo_feeds.json`), found automatically, credited to the outlet and
     photographer, used for news and commentary. Agency photos (Getty, AFP, Reuters, AP...) are skipped.
  4. **Symbolic**: a real Kenyan place or object that stands for the story, or a landmark when nothing fits.
  Every card says which one it carries; the credit goes on the design and in the caption.

### Formats (calendar.json)
Sauti ya Mwananchi · Set It Straight · Follow the Money · Promise Tracker · Chapter Six Test · scam alerts ·
Your Say polls (Thursday and Sunday) · daily hot post · **Tazama Hii** (clips you send) · Hatutasahau
anniversaries. Every post also ships as a 9:16 Reel told in beats.

## Running it (GitHub → Actions → autopilot → Run workflow)

| Command | What it does |
|---|---|
| `this-week` | Plan and draft the current week now |
| `remake` | Re-plan the rest of this week from the current calendar and redraft (costs AI credit) |
| `redo` | Redraft only the posts the checks held back |
| `rephoto` | Same words, new photos, re-sent |
| `hot` | Today's post on the biggest story + the trend radar |
| `radar` | Live X trends and the most-watched Kenyan clips, to Telegram |
| `reels` | Re-send this week's Reels waiting for your decision |
| `clips` | Turn videos you sent the bot into Tazama Hii Reels now |
| `samples` | Profile kit + sample comment cards |
| `photocheck` | Explain this week's photo searches (`automation/state/photos.log`) |
| `rehearse` | A full mock week, no keys, nothing sent |

### Tazama Hii: sending a clip
Send the video to the bot. The caption's **first line** says where it came from, then what it's about:
`ruhusa @who (how they agreed)` · `yangu` (we filmed it) · `nukuu Citizen TV https://link` (news quote, max 8 s).
Under 20 MB. Without that line the clip is never used.

## Secrets (GitHub → Settings → Secrets and variables → Actions)

| Secret | For |
|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Approvals (set) |
| `GEMINI_API_KEY` | The free writer (aistudio.google.com/apikey). Without it the paid Claude key is used |
| `ANTHROPIC_API_KEY` | Paid writer (set). Optional passes stop at `JUA_WEEKLY_BUDGET_USD` (default $0.50 a run) |
| `META_ACCESS_TOKEN`, `META_PAGE_ID`, `META_IG_USER_ID` | Publishing, comments, insights (Page token; see below) |
| `PEXELS_API_KEY` | Optional extra photo source |

**Meta token:** developers.facebook.com → app (Business) → Graph API Explorer → permissions
`pages_show_list, pages_read_engagement, pages_manage_posts, pages_manage_engagement, instagram_basic,
instagram_content_publish, instagram_manage_comments, instagram_manage_insights, business_management` →
Generate → Access Token Tool → Extend → `me/accounts` gives the Page id and the non-expiring Page token →
`<page-id>?fields=instagram_business_account` gives the Instagram user id.

## Files

```
automation/pipeline.py     plan → draft → render → Telegram → publish → learn; every command above
automation/draft.py        the writer + editor (Gemini free, or Claude with a budget cap)
automation/guard.py        every content check
automation/demand.py       what Kenya is on, ranked
automation/radar.py        X trends + Kenyan TV clips (no keys)
automation/news.py         headlines (content/news_feeds.json)    automation/trends.py  Google Trends Kenya
automation/photos.py       licensed real photos + face check (content/models/: YuNet, MIT)
automation/render.py       HTML templates → PNG, visual QA         automation/video.py   Reels (beats, sound)
automation/tazama.py       clips → commentary Reels               automation/engage.py  comment replies
automation/presence.py     highlight covers + profile kit         automation/templates/ one template per format
automation/calendar.json   the weekly rhythm                      automation/content/   nicknames, anniversaries, feeds, music
automation/state/          approvals, evidence file, radar, photo log (committed by the bot)
automation/tests/          the test suite (no network needed)
.github/workflows/autopilot.yml
```

## Before you tap ✅
- Open the source on any post that names a public office holder. For high-stakes claims, ask a media lawyer first.
- Reject anything whose photo could be read as a real person it isn't.
- Rotate any token that is ever pasted somewhere public. Never commit `.env`.
