# Music for Reels

Only tracks we have the right to use go here, so posts are never muted or taken down.

1. **Kenyan and African artists, with permission** (best: it's a Put Us On for them).
   DM or email the artist, ask to use 15 seconds of a track in Jua Kesho Reels with credit. Keep the reply.
2. Add the file here (mp3/wav/m4a) and an entry in `tracks.json`:

```json
{"file": "amina-kesho.mp3", "artist": "Amina", "title": "Kesho", "start": 32.5,
 "rights": "permission by email, 12 Oct 2026", "handle": "@amina"}
```

3. A post uses it with `"track": "amina-kesho.mp3"`. The Reel starts at `start` seconds (pick the hook),
   fades in and out, is balanced for phone speakers, and the caption credits the artist.

Trending sounds on TikTok/Instagram can't be added through the API: add those by hand in the app when you
post, from the platform's own licensed library.
