"""
kenyan_sound.py — real Kenyan music under our Reels, legally: Instagram's own licensed library.

Instagram's Audio API (GET /ig_audio, then audio_configuration on POST /{ig-user-id}/media) attaches a track from
the music Instagram has licensed "for third party use" to a Reel published through the API, with the song's name
on the Reel, so a viewer can tap through to the artist. That is the only route that puts a real song under our
video without a licence from its owner: a song mixed into our own MP4 is copied without permission (YouTube's
Content ID claims or blocks it, Instagram mutes it) and pays the artist nothing.

What is Kenyan and trending comes from YouTube's most-popular music chart for Kenya, kept to channels registered in
Kenya (the channel's own country field), so Tanzanian and Nigerian hits on the Kenyan chart are not taken for Kenyan.

    python pipeline.py audiocheck      # what the chart and Instagram's library offer right now (reads only)
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

YT = "https://www.googleapis.com/youtube/v3/"
GENRES = ("gengetone", "arbantone", "kenyan drill")   # Nairobi's street and urban sounds, searched by name too


def _yt(path: str, q: dict) -> dict:
    with urllib.request.urlopen(YT + path + "?" + urllib.parse.urlencode(q), timeout=60) as r:
        return json.loads(r.read() or b"{}")


def kenyan_chart(key: str, n: int = 30) -> list[dict]:
    """Songs on YouTube's Kenya music chart whose channel is registered in Kenya: [{"artist", "song", "title",
    "channel", "views", "url"}], most viewed per day first. Reads only."""
    import datetime as dt
    import mtaa
    items = _yt("videos", {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": "KE",
                           "videoCategoryId": "10", "maxResults": 50, "key": key}).get("items", [])
    ids = sorted({v["snippet"]["channelId"] for v in items})
    country = {}
    for i in range(0, len(ids), 50):
        for c in _yt("channels", {"part": "snippet", "id": ",".join(ids[i:i + 50]), "key": key}).get("items", []):
            country[c["id"]] = (c.get("snippet") or {}).get("country", "")
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for v in items:
        s, st = v["snippet"], v.get("statistics", {})
        artist, song = mtaa.split_title(s["title"], s.get("channelTitle", ""))
        days = max((now - dt.datetime.fromisoformat(s["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 86400, 1)
        out.append({"artist": artist, "song": song, "title": s["title"], "channel": s.get("channelTitle", ""),
                    "country": country.get(s["channelId"], ""), "per_day": round(int(st.get("viewCount", 0)) / days),
                    "url": f"https://www.youtube.com/watch?v={v['id']}"})
    out.sort(key=lambda x: -x["per_day"])
    return out[:n]


def ig_search(graph_get, ig_user: str, query: str | None = None) -> list[dict]:
    """Instagram's licensed music for a search ("artist song"), or what is trending when query is None."""
    fields = {"audio_type": "music", "user_id": ig_user}
    if query:
        fields["search_query"] = query
    got = graph_get("ig_audio", fields)
    return list(got.get("audio") or got.get("data") or [])


def check(graph_get, log) -> bool:
    """Prints the Kenya chart (with each channel's country) and what Instagram's library has for each Kenyan song,
    for the urban genres and for trending. Reads only; returns whether Instagram's audio search answered."""
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    ig = os.environ.get("META_IG_USER_ID", "").strip()
    chart = []
    try:
        chart = kenyan_chart(key)
        for c in chart:
            log(f"chart {c['per_day']:>8}/day  [{c['country'] or '--'}] {c['artist']} - {c['song']}  ({c['channel']})")
    except Exception as e:
        log(f"chart not read: {str(e)[:200]}")
    answered = False
    queries = [None] + list(GENRES) + [f"{c['artist']} {c['song']}" for c in chart if c["country"] == "KE"][:15]
    for q in queries:
        try:
            hits = ig_search(graph_get, ig, q)
            answered = True
        except Exception as e:
            log(f"ig_audio {q or 'trending'}: FAILED {str(e)[:300]}")
            continue
        log(f"ig_audio {q or 'trending'}: {len(hits)} track(s)")
        for h in hits[:6]:
            log(f"    {h.get('display_artist') or h.get('ig_username') or '?'} - {h.get('title')} "
                f"({round((h.get('duration_in_ms') or 0) / 1000)}s, id {h.get('audio_id') or h.get('id')})")
    return answered
