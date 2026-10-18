"""YouTube Shorts upload for approved Reels. Optional: runs only when the three YT_* secrets exist.

Kenya is in YouTube's Partner Programme, so Shorts is the one monetisation route open to the channel today.
Standard library only, like the rest of the pipeline.

One-time setup (on your own computer, never in chat):
  1. Google Cloud console → new project → enable "YouTube Data API v3".
  2. Credentials → OAuth client ID → type "TVs and Limited Input devices". Put the ID and secret in the
     environment as YT_CLIENT_ID and YT_CLIENT_SECRET.
  3. `python youtube.py auth` → open the link it prints, enter the code, sign in with the channel's Google account.
  4. Save the three values as GitHub secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KEYS = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEVICE_URL = "https://oauth2.googleapis.com/device/code"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
SCOPE = "https://www.googleapis.com/auth/youtube"   # the device flow allows only this and youtube.readonly
MAX_DESC = 4800   # YouTube's limit is 5,000 bytes


def ready() -> bool:
    return all(os.environ.get(k) for k in KEYS)


def _post(url: str, fields: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read() or b"{}").get("error", str(e.code)), "http": e.code}


def access_token() -> str:
    r = _post(TOKEN_URL, {"client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
                          "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    if "access_token" not in r:
        raise RuntimeError(f"YouTube sign-in failed: {r.get('error')}")
    return r["access_token"]


def body(title: str, description: str) -> dict:
    return {"snippet": {"title": title[:100], "description": description[:MAX_DESC],
                        "categoryId": "25"},   # News & Politics
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}


def upload(video: Path, title: str, description: str) -> dict:
    """Resumable upload. Returns {"id", "privacy"}; privacy shows when YouTube forced the video to private."""
    token = access_token()
    data = Path(video).read_bytes()
    meta = json.dumps(body(title, description)).encode()
    start = urllib.request.Request(UPLOAD_URL, data=meta, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(data))})
    try:
        with urllib.request.urlopen(start, timeout=60) as r:
            session = r.headers["Location"]
        put = urllib.request.Request(session, data=data, method="PUT",
                                     headers={"Content-Type": "video/mp4", "Content-Length": str(len(data))})
        with urllib.request.urlopen(put, timeout=600) as r:
            done = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"YouTube upload → {e.code}: {e.read().decode(errors='replace')[:400]}") from e
    if not done.get("id"):
        raise RuntimeError("YouTube upload returned no video id")
    return {"id": done["id"], "privacy": (done.get("status") or {}).get("privacyStatus", "unknown")}


def auth() -> None:
    """Device-code sign-in; prints the refresh token to save as YT_REFRESH_TOKEN."""
    cid, secret = os.environ.get("YT_CLIENT_ID"), os.environ.get("YT_CLIENT_SECRET")
    if not (cid and secret):
        sys.exit("Set YT_CLIENT_ID and YT_CLIENT_SECRET first.")
    d = _post(DEVICE_URL, {"client_id": cid, "scope": SCOPE})
    if "device_code" not in d:
        sys.exit(f"Google refused: {d.get('error')}")
    print(f"Open {d['verification_url']} and enter the code {d['user_code']}", flush=True)
    deadline = time.time() + int(d.get("expires_in", 1800))
    while time.time() < deadline:
        time.sleep(int(d.get("interval", 5)))
        r = _post(TOKEN_URL, {"client_id": cid, "client_secret": secret, "device_code": d["device_code"],
                              "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if r.get("refresh_token"):
            print("\nSave this as the GitHub secret YT_REFRESH_TOKEN:\n" + r["refresh_token"])
            return
        if r.get("error") not in ("authorization_pending", "slow_down"):
            sys.exit(f"Sign-in failed: {r.get('error')}")
    sys.exit("The code expired. Run it again.")


if __name__ == "__main__":
    auth() if sys.argv[1:] == ["auth"] else sys.exit("usage: python youtube.py auth")
