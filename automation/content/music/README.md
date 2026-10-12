# Music for Reels

Real music, used legally, so posts are never muted or taken down. Three ways:

**A. Trending sounds (the strongest for reach).** On Telegram, tap **🎵 I'll post it** on a Reel. The bot stops
there and sends you the caption. In Instagram or TikTok tap *Add audio*, pick a trending Kenyan sound and turn
*Original audio* to 0. The platform licenses that music. (The API can't add library music, so this is manual.)

**B. Tracks in this folder (automatic).** Every Reel picks one by mood: `"urgent"` for civic posts, `"uplifting"`
for good news (`"any"` fits both). Only tracks with recorded rights and `"clean": true` are ever used.
Where to get them legally:
- Kenyan and African artists, with permission (best, see below).
- Pixabay Music (pixabay.com/music): free for commercial use, including social video. Check the track page:
  skip any track marked as registered with Content ID (it can trigger claims on YouTube/Facebook).
- Free Music Archive (freemusicarchive.org): only tracks licensed **CC BY** (not NC, ND or SA). Credit the artist.

**C. Nothing in the folder:** the Reel uses the original synthesised bed (silent Reels don't get recommended).

1. **Kenyan and African artists, with permission** (best: it's a Put Us On for them).
   DM or email the artist, ask to use 15 seconds of a track in Jua Kesho Reels with credit. Keep the reply.
2. Add the file here (mp3/wav/m4a) and an entry in `tracks.json`:

```json
{"file": "amina-kesho.mp3", "artist": "Amina", "title": "Kesho", "start": 32.5, "mood": "uplifting",
 "rights": "permission by email, 12 Oct 2026", "handle": "@amina", "clean": true}
```

3. Set `"clean": true` only after listening: the part we use has no explicit lyrics (clean for everyone
   applies to sound too). Tracks without it are never used.
4. A post uses it with `"track": "amina-kesho.mp3"`. The Reel starts at `start` seconds (pick the hook),
   fades in and out, is balanced for phone speakers, and the caption credits the artist.

Trending sounds on TikTok/Instagram can't be added through the API: add those by hand in the app when you
post, from the platform's own licensed library.
