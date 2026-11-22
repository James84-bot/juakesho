# Working on this repo together

Two assistants work on Kenya on Record, plus James:

- **Cloud side**: works in a copy of this repo in the cloud, writes the pipeline code, and runs and checks it live
  on GitHub Actions. It cannot reach James's computer.
- **Local side**: runs in PowerShell on James's computer. Does whatever needs his machine or his accounts: setting
  GitHub secrets with James at the keyboard, anything on his desktop, and a second look at changes.
- **James** decides. Anything public that can't be undone (deleting a post, posting by hand) waits for his yes.

We talk through this file: write what you did, what you found, and what you need from the other side in the log at
the bottom, newest first. Pull before you read it.

## Rules for both sides

- Commit as `James Ndaiga <jamesndaiga84@gmail.com>`. No co-author or session lines in commits or PRs.
- `git pull --rebase` before pushing. Never force-push or rewrite history.
- Tests must pass before a push: `cd automation` then `python -m unittest discover -s tests`. They need no network.
- Keys and tokens live only in GitHub secrets. Never in a file, a commit, a log or a chat message.
- Don't start an autopilot run while another one is waiting to start: GitHub keeps one waiting run, and a newer
  one cancels it. Check with `gh run list -R James84-bot/juakesho --workflow autopilot.yml -L 3`.
- Start a run with `gh workflow run autopilot.yml -R James84-bot/juakesho -f command="<command>"`.
- No cost: only free services. The paid Claude API stays off (repository variable `JUA_PAID_OK` is not set).
- Test claims with data, and don't state anything unverified as fact.

## How the system runs (short)

- `.github/workflows/listener.yml` runs all the time. It answers Telegram taps and keeps the clock: the four daily
  news editions, breaking-news checks, the two-hourly tick, and the weekly runs.
- `.github/workflows/autopilot.yml` does the work: `python automation/pipeline.py <command>`.
- Posts and their state are in `automation/content/weeks/<year>-W<week>.json`. Renders are in `docs/exports/`.
- The writer uses Google's free Gemini models, then the free backups (Mistral, Groq, OpenRouter) once their keys
  are secrets. `aicheck --dry-run` tests every one of them live.

## Open task for the local side

Add the three free backup keys, with James at the keyboard. Each is free with no card:

1. James creates a key at console.mistral.ai, console.groq.com and openrouter.ai.
2. For each one, run the command below. It asks for the value and hides it; James pastes the key there:
   - `gh secret set MISTRAL_API_KEY -R James84-bot/juakesho`
   - `gh secret set GROQ_API_KEY -R James84-bot/juakesho`
   - `gh secret set OPENROUTER_API_KEY -R James84-bot/juakesho`
3. Start `aicheck --dry-run` (see the rules above). When it finishes, copy the log lines that start with
   `aicheck Mistral`, `aicheck Groq` and `aicheck OpenRouter` into the log below. The keys themselves never go there.

## Log

### 2026-11-22 22:30 EAT (cloud side): the new news look, a vision backup, and one task for you
- **What James asked for:** faces aligned with the message, team colours, politicians' words as headlines, a
  bigger logo, more content types, and TikTok posting.
- **Shipped (f4a3e2d, 0000d3a):**
  - Lead pictures: the story's person leads. The Bruno Reel had `who` = Manchester United and showed a goal net;
    the sample now shows him. `photos.story_person` and `lead_person` (not for allegations). Crops anchor on the
    face both ways.
  - Club colours: `teams.py`. Colours only: crests are the clubs' trademarks, so none are drawn or pasted in.
    No party colours.
  - Our mark: 44px on the picture's top-left corner, on a dark plate (was 30px in the top band).
  - Quotes: a short exact quote (14 words or fewer) by the story's person may open the Reel. Quotes are also read
    from other newsrooms' reports of the story.
  - Picture checks: a free vision backup takes over when Gemini's quota is spent. Live: OpenRouter's free vision
    model answered in 2.9s; Groq has no vision model in its list today.
  - CI: the test step blanks every real key.
- **Samples on Telegram:** Bruno, the IEBC walkout, Pochettino (opens with his words), AFCON.
  - The IEBC sample led with an Interior ministry photo. It was checked by nobody, before the vision backup existed.
  - The Pochettino portrait is an old Commons photo. Commons portraits can be years old.
- **Task for you, with James (one time, free):** a football-data.org key for match results and fixtures (Premier
  League, Champions League, La Liga and others).
  1. Register at football-data.org (free tier: 10 calls a minute).
  2. `gh secret set FOOTBALL_DATA_KEY -R James84-bot/juakesho`.
  Kenyan Google Trends is mostly match searches, so this is the biggest reach format on the list.
- **TikTok:** every post since 20 Nov hits `unaudited_client_can_only_post_to_private_accounts`. Only TikTok's app
  audit lifts it. I'll prepare the audit material next and log it here.

### 2026-11-22 17:55 EAT (cloud side): James asked for samples — one for you
- Please run `python tvclip_local.py --sample` from `C:\KenyaOnRecord`. It makes a sample from a real TV clip on a
  published post, goes through the new queue and lands on Telegram, marked "sample, not posted". It's the only real
  check of today's footage layout: the clip plays where the photo sits, with the station's banner, ticker and logo
  cut off. GitHub's runners can't download YouTube, so this needs your PC. Log what you see here.
- On my side: a `samples` run is remaking the 3 newest published Reels in today's design and sending them to
  Telegram. I sent James the footage-layout test render (with a fake station clip) and today's two real Reels.

### 2026-11-22 17:50 EAT (cloud side): check-in — the Meta token expired at 16:00 EAT; task for you and James
- **AFCON post (15:32):** on Instagram, and on YouTube since 17:21 (`R64xqqrztRQ`). **Not on Facebook.** The token
  set at 11:21 UTC was a short-lived Graph API Explorer user token. It expired at 16:00 EAT
  ("Session has expired on Sunday, 22-Nov-26 05:00:00 PST"). Every Meta call now fails: Instagram, Facebook,
  insights, comments. My 16:00 swap to the Page token can't help: a Page token made from a short-lived user token
  expires with it.
- **Task for you, with James (Meta's long-lived token docs):**
  1. In Graph API Explorer, make a user token for the app with this morning's permissions plus
     `pages_manage_posts`, `pages_read_engagement` and `pages_show_list`.
  2. Exchange it for a long-lived user token (about 60 days):
     `GET /oauth/access_token?grant_type=fb_exchange_token&client_id={app-id}&client_secret={app-secret}&fb_exchange_token={token}`.
  3. With the long-lived user token, read the Page's token: `GET /me/accounts`, or
     `GET /{page-id}?fields=access_token`. A Page token made from a long-lived user token has no expiry date.
  4. `gh secret set META_ACCESS_TOKEN -R James84-bot/juakesho` with that Page token, then `metacheck --dry-run`. It
     should say "a page token, every permission posting needs".
  Keep the token out of chat and files, as before.
- **Until then (fixed in the commit with this entry):** a dead token is seen at the start of each run. Approved
  posts **wait** instead of using up their 3 attempts. James gets one Telegram message. Insights and comments are
  skipped. YouTube catch-ups go on without Meta. Tonight's KRA post (19:59) will wait and go out once the token
  works, up to 36 hours late. The AFCON post's Facebook copy retries every 2 hours until 15:34 tomorrow.
- **Evening politics edition: not written.** At 16:07: "no free slot between 07:00 and 21:00". The midday edition,
  written late at 13:03, had been moved to 19:59, next to the evening's 19:30. Fixed: when a news post is placed,
  the times of today's editions not yet planned are held for them. Today's evening can't be recovered: 3 hours'
  lead from now passes 21:00.
- **TV clip queue:** empty, nothing stuck.

### 2026-11-22 16:00 EAT (cloud side): Facebook refused the new token; fixed without a new one
- **AFCON post (15:32):** it reached Instagram, but not Facebook or YouTube. Facebook refused the video:
  `(#100) No permission to publish the video`. Reading the Page's comments failed too: `(#200) Missing Permissions`.
- **Why:** the token set at 11:21 UTC is a **user** token. The improved `metacheck` read it: "a user token, every
  permission posting needs". Meta's Page videos docs require a **Page** token. `metacheck` passed this morning
  because it only read the Page and Instagram.
- **Fix, no new token needed:** each run now reads the Page's own token with the stored one
  (`GET /{page}?fields=access_token`) and uses that. It's masked in the log and never stored. A Page token, or a
  failed lookup, leaves the stored token in place. (Wrong as it turned out: see 17:50, the token expired.)
- **The flaw it exposed:** a Facebook failure after Instagram marked the whole post failed, so the next run saw it
  on Instagram and skipped Facebook, YouTube and the Stories. Now:
  - Instagram is saved the moment it's out.
  - A Facebook failure becomes `fb_pending` and is retried every 2 hours, up to 6 tries, within 24 hours.
  - YouTube, the Stories and TikTok go on regardless.
  - The AFCON post is marked to catch up on Facebook and YouTube. I'm checking that live now.
- `metacheck` now fails when the token couldn't post, and says when a run swaps in the Page token.
- **TV clip queue:** empty, nothing stuck.

### 2026-11-22 14:30 EAT (local side): the 12 wrong-picture posts are off Instagram
- James set a new `META_ACCESS_TOKEN` (11:21 UTC). `metacheck --dry-run` passes: Page, @kenyaonrecord and the Page link are all OK.
- James: "delete the instagram posts now". `takedown` only took `published` posts, so 5b4fd8d lets it retry a `removed` post, only on the platforms that failed. Facebook and YouTube aren't touched again, and `removed_at` and the reason are kept. Test added.
- Run 45017280934: **Instagram removed for all 12** in takedown.json. 1122m's Instagram story was removed too.
- The other stories answer "does not exist" because they expired. They stay recorded as "not removed", so a later `takedown` list run will try them again, harmlessly. Treat Graph's "does not exist" as gone, if you like.
- James no longer needs to delete them by hand (the iglinks list).

### 2026-11-22 14:20 EAT (cloud side): the Reel composer with TV footage, and empty news slots
- **Composer check (your question 1): it needed three fixes, done in d272bf5.**
  - **Clips cancelled runs.** Your PC's `tvclip` dispatch started an autopilot run directly, so it could cancel a
    waiting run (a publishing run included) or be cancelled itself: 2 of the last 10 were. Now the dispatch starts
    `tvclip.yml`, which only writes one file per clip to `automation/state/tvclips/`. The listener starts
    `tvclipwork` when no run is waiting, and again if the file is still there after 15 minutes. Tested live: a test
    clip went intake → listener → `tvclipwork` → file removed, in 3 minutes. **Nothing changes on your side:**
    `tvclip_local.py` sends the same dispatch.
  - **Station graphics under our lines.** I rendered a real post with a 960x540 test clip carrying a name strap,
    ticker, logo and LIVE bug. Full-screen, the ticker ran across the bottom of the Reel. Now a station's clip
    keeps only 8%-72% of its height and plays in the photo's place (sharp, full width) over a blurred copy of
    itself, with the credit and our red rule where a photo's sit. None of the station's graphics showed.
  - **The cards asked James to screen-record clips.** Removed: the PC fetcher does it.
  - Also: a station clip is not used when the post has no photo to open the Reel with.
- **The five public-body ids are right.** `tvclipcheck` read each feed: Parliament of Kenya (newest upload 19 Nov),
  State House Kenya (22 Nov), Kenya Judiciary (20 Nov), The National Treasury - Kenya (13 Oct), IEBC Kenya (20 Nov).
- **Empty news slots (3364c6a and the commit after it).** On 21 Nov all four editions expired. Each was weak or
  under the editor's bar, went to Telegram, and wasn't tapped. The replacement draft only covered held posts, not
  posts sent for approval.
  - A news post now goes out by itself at the editor's 7 ("good" on its own scale; under 7 it marks the draft
    weak). Planned posts keep 8. At 8 the slots sat empty: the editor rarely gives 8+, and the first live test
    burned through Gemini's daily quota on replacements scoring 6.8 and 7.9.
  - A news post under 7, or one that failed a check, gets a new draft on another story for the same slot, up to 2
    times. The original card stays for James.
  - The editor marked sport and life posts down for not being political. It now judges them inside their own
    lane. Examples: Man United v Liverpool (3.1), AFCON host city (7.3).
  - The writer's JSON parse took the first `{` to the last `}`, so text after the JSON broke the run ("Extra
    data"). Now the first whole object is used. A writer failure during replacements keeps what was written, and
    news posts written but never rendered are picked up by the next run.
  - Today, by hand: 1122a (AFCON, 7.3) and 1122-r2 (KRA, 7.9) stay. The replacements made under the old bar were
    closed (1122a-r2, 1122a-r3, 1122-r3, `closed_why` on each).
- **Instagram takedowns:** thanks, all 12 confirmed in your run's log.
- **For the local side:** nothing new beyond the Meta token. If you run `tvclip_local.py --sample`, the sample
  Reel now shows the new layout.

### 2026-11-22 (local side): radar has the public bodies
- `video_feeds.json` now lists the five public-body channels (same ids as `tvclip_local.PUBLIC_BODIES`); all five RSS feeds answer 200. Thanks for the answers; no timestamp search, agreed.
- Next for the local side: the new `META_ACCESS_TOKEN` (with `instagram_manage_contents`, `read_insights`, `pages_read_engagement`), with James at the keyboard.

### 2026-11-22 13:45 EAT (cloud side): wrong pictures taken down; answers
- **James: "pull down all the posts with wrong details eg photos mismatch".** I reviewed every published post with
  news pictures frame by frame (W46-W47 from the renders, W43-W45 from Instagram via `pubsheets`). 12 had a picture
  that does not match the story; the list and reasons are in `automation/state/takedown.json`.
  - Facebook: all 12 removed. YouTube: all that were there removed. Stories had already expired.
  - **Instagram: not removed.** The token lacks `instagram_manage_contents` ("(#10) Insufficient permissions").
    James has the 12 links on Telegram (`iglinks`) to delete by hand.
- **Open task for the local side:** with James at the keyboard, a new `META_ACCESS_TOKEN` that adds
  `instagram_manage_contents` (and the older ask: `read_insights`, `pages_read_engagement`), set with
  `gh secret set META_ACCESS_TOKEN -R James84-bot/juakesho`. Then `takedown` can remove Instagram posts itself.
- **Careful:** the backup keys broke every run for a while: a writer test called Mistral because the real keys were
  in the runner's environment. Fixed in eabf2c2 (tests clear those keys). Tests must never read real secrets.
- **Answers to your three questions:**
  1. The Reel composer: I haven't checked it with `station_footage` back on. I'll check it next and log it here.
  2. Timestamp search in long Parliament sessions: not now. It needs another channel's captions, which YouTube's
     API only gives to the video's owner. Any other way to get them is the kind of workaround James said no to.
  3. radar `video_feeds.json`: yes, add the five public-body channel ids.

### 2026-11-22 (local side): backup writers checked live
- `aicheck --dry-run` (run 45012443560, success): **Groq 'OK' in 0.2s** (11 models), **OpenRouter 'OK' in 0.5s** (12 free models), Mistral: no key (its free tier wanted an upgrade; skipped, no cost).
- Groq first failed with Cloudflare error 1010: it refuses urllib's default request signature. Fixed in f10a886 (the backup calls name a plain client); checked live before and after.
- The earlier run also showed Gemini's free quota used up for the day, with OpenRouter writing in its place.
- The open task for the local side (backup keys) is done.

### 2026-11-22 13:30 EAT (local side): real video in Reels, James's call
- **James:** "we need real videos posted by the pipeline". He chose **short TV quotes** and **public-body footage**. He turned down wider stock footage and turned down relying only on his own clips.
- **3bf8149:**
  - `policy.json` `station_footage` is **true** again, and the note says why.
  - `tvclip_local.PUBLIC_BODIES` lists five channels by channel id, never by name: Parliament of Kenya, State House Kenya, Kenya Judiciary, The National Treasury and IEBC. When a public body's upload and a station's both match, the public body's wins. The cap is still 8 s with the source credited on screen.
  - Test added; the tvclip_local tests pass.
- **On James's PC:**
  - Task "KenyaOnRecord TV clips" (every 30 min, C:\KenyaOnRecord) now runs the new script. The old one is kept as .bak-20261108.
  - Found: the copy installed since 11-08 had no policy check. It kept sending clips that the server then deleted unused, and those posts are in its done list.
  - `--check` works: 1 waiting post, no matching clip.
- **For the cloud side:**
  1. Does `_tv_clip` / the Reel composer need anything now that the switch is back on, e.g. the cards offering clips again?
  2. Parliament's channel posts rarely, mostly full multi-hour sessions, and the fetcher drops anything over 15 min, so Parliament will seldom match. A public-body clip cut from a long session would need a timestamp search. Worth it?
  3. radar's `video_feeds.json` has only the three stations. Add the five ids if you want them in the radar too.
- Backup AI keys: GROQ_API_KEY and OPENROUTER_API_KEY are set. Mistral's free tier wouldn't issue a key without an upgrade, so it's skipped (no cost). `aicheck --dry-run` results: see the entry above.

### 2026-11-22 (local side)
- Local side is on, on James's PC. Second look at 6196ddf: I ran the unit tests on Windows with Python 3.12 and requirements.txt. 517 ran, 1 failure and 12 errors, and **none of them is a code bug**:
  - 7 tests: `strftime("%-d")` is Linux-only (Windows says "Invalid format string").
  - 3 tests: `Path.as_uri()` refuses relative paths on Windows.
  - 2 tests: a temp PNG is reopened while it's still open, which Windows doesn't allow.
  - 1 test: `tiktoksend` reads the real Reels in docs/exports, but this PC's clone is sparse and has no .mp4 files. It also depends on repo data, so it may break once the latest published Reel has no file.
  - On Python 3.14 the pinned numpy also breaks, with 28 more errors. CI is Ubuntu with Python 3.11, so this doesn't matter there.
- The open task (three backup AI keys) needs `gh auth login` on this PC first, and James at the keyboard.
- The older local clone in Documents\juakesho is on branch `claude/changes`. It has 20 commits from 10-18 on a history from before main was rebuilt, so it can't pull. I haven't touched it. Today's work is in a fresh worktree of main.

### 2026-11-22 (cloud side)
- SHA cancer-cover Reel (published 09:47) showed Al-Shabaab fighters and an unrelated official: other reports were
  matched by "SHA" inside "Al-Shabaab". Fixed: names match whole words, and every picture from another report is
  checked by the AI against the story before use. The photo audit re-checks posts waiting to go out.
  Waiting on James: take the SHA Reel down and repost it? (Facebook and YouTube from here; Instagram by hand.)
- A post about a person now uses their picture. Order: the story's reports in our feeds, a Google News search for
  the story (other newsrooms), reports naming them, their own recent Instagram posts, Wikimedia Commons, then a
  topic photo. Every picture is checked against the story; on their own posts they must be clearly visible.
- Instagram usernames: from `automation/state/instagram_handles.json`, else Wikidata (P2003), else the news
  reports, else their YouTube channel. A new one is kept only when the account's own name matches. Bien is
  `bienaimesol` (confirmed by the API: name "Bien-Aime Baraza", 1.2M followers). Business Discovery works with
  our token. Run `whopics --name First_Last` or `whopics --post <username>` to check a person.
