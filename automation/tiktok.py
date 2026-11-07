"""TikTok upload for approved Reels through the Content Posting API (Direct Post). Optional: runs only when the
three TIKTOK_* secrets exist. Standard library only, like the rest of the pipeline.

Until TikTok audits the app, every post it accepts is private (SELF_ONLY). upload() asks for a public post first and
falls back to private when TikTok answers `unaudited_client_can_only_post_to_private_accounts`, and it reports which
one it got, so a private post is never mistaken for a public one.

One-time setup (on your own computer, never in chat):
  1. developers.tiktok.com → your app → Products: Login Kit + Content Posting API; Scopes: user.info.basic, video.publish.
  2. Login Kit → Redirect URI: https://james84-bot.github.io/juakesho/
  3. Put the client key and secret in the environment as TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET.
  4. `python tiktok.py auth` → open the link it prints, approve as the TikTok account, paste the address you land on.
  5. Save the three values as GitHub secrets: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN.
"""
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

KEYS = ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN")
API = "https://open.tiktokapis.com/v2"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
REDIRECT_URI = "https://james84-bot.github.io/juakesho/"   # registered in the app's Login Kit settings
SCOPES = "user.info.basic,video.publish"
MAX_TITLE = 2200          # TikTok counts UTF-16 units; slicing by characters stays under it for our text
ONE_CHUNK_MAX = 64 * 1024 * 1024
CHUNK = 32 * 1024 * 1024  # used only for files over 64 MB
UNAUDITED = "unaudited_client_can_only_post_to_private_accounts"


class TikTokError(RuntimeError):
    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


def ready() -> bool:
    return all(os.environ.get(k) for k in KEYS)


def _request(url: str, *, data: bytes | None = None, headers: dict | None = None, method: str = "POST",
             timeout: int = 60) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def _json(raw: bytes) -> dict:
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {}


def _token_call(fields: dict) -> dict:
    status, _, raw = _request(f"{API}/oauth/token/", data=urllib.parse.urlencode(fields).encode(),
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
    r = _json(raw)
    if "access_token" not in r:
        raise TikTokError(f"TikTok sign-in failed ({status}): {r.get('error_description') or r.get('error') or raw[:200]!r}",
                          str(r.get("error") or ""))
    return r


def access_token() -> str:
    """A fresh 24-hour access token from the saved refresh token (valid 365 days)."""
    r = _token_call({"client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
                     "grant_type": "refresh_token", "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"]})
    new = r.get("refresh_token")
    if new and new != os.environ["TIKTOK_REFRESH_TOKEN"]:
        # TikTok may rotate it. The old one keeps working until it expires, but say so, never print the value.
        print("::warning title=tiktok::TikTok issued a new refresh token; re-run `python tiktok.py auth` "
              "and update TIKTOK_REFRESH_TOKEN before the old one expires.")
    return r["access_token"]


def _api(path: str, token: str, payload: dict | None = None) -> dict:
    status, _, raw = _request(f"{API}{path}", data=json.dumps(payload or {}).encode(),
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json; charset=UTF-8"})
    r = _json(raw)
    err = r.get("error") or {}
    if err.get("code", "ok") != "ok" or status >= 400:
        raise TikTokError(f"TikTok {path} → {status} {err.get('code')}: {str(err.get('message'))[:300]}",
                          str(err.get("code") or ""))
    return r.get("data") or {}


def creator_info(token: str) -> dict:
    return _api("/post/publish/creator_info/query/", token)


def check() -> str:
    """Sign in with the three secrets and read the account's username. Uploads nothing."""
    info = creator_info(access_token())
    return info.get("creator_username") or info.get("creator_nickname") or "unknown"


def chunks(size: int) -> list[tuple[int, int]]:
    """(first_byte, last_byte) for each chunk. One request up to 64 MB; above that 32 MB chunks, with the
    leftover bytes merged into the last one (TikTok's rule: total = size // chunk_size)."""
    if size <= ONE_CHUNK_MAX:
        return [(0, size - 1)]
    total = size // CHUNK
    return [(i * CHUNK, (i + 1) * CHUNK - 1 if i < total - 1 else size - 1) for i in range(total)]


def _init(token: str, title: str, size: int, privacy: str) -> dict:
    plan = chunks(size)
    first = plan[0]
    return _api("/post/publish/video/init/", token, {
        "post_info": {"title": title[:MAX_TITLE], "privacy_level": privacy, "brand_content_toggle": False,
                      "brand_organic_toggle": False, "is_aigc": False},
        "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                        "chunk_size": size if len(plan) == 1 else first[1] - first[0] + 1,
                        "total_chunk_count": len(plan)}})


def _put(upload_url: str, data: bytes) -> None:
    size = len(data)
    plan = chunks(size)
    for i, (lo, hi) in enumerate(plan):
        part = data[lo:hi + 1]
        status, _, raw = _request(upload_url, data=part, method="PUT", timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(len(part)),
            "Content-Range": f"bytes {lo}-{hi}/{size}"})
        if status not in (201, 206):
            raise TikTokError(f"TikTok video upload (part {i + 1}/{len(plan)}) → {status}: {raw[:300]!r}")


def status(token: str, publish_id: str, wait: int = 150) -> dict:
    """Polls until the post settles or `wait` seconds pass. Returns TikTok's status object."""
    deadline = time.time() + wait
    while True:
        s = _api("/post/publish/status/fetch/", token, {"publish_id": publish_id})
        if s.get("status") in {"PUBLISH_COMPLETE", "FAILED", "SEND_TO_USER_INBOX"} or time.time() >= deadline:
            return s
        time.sleep(5)


def upload(video: Path, title: str, wait: int = 150) -> dict:
    """Posts the video. Returns {"publish_id", "privacy", "status", "fail_reason"}; privacy is what TikTok accepted."""
    token = access_token()
    options = creator_info(token).get("privacy_level_options") or ["SELF_ONLY"]
    data = Path(video).read_bytes()
    order = [p for p in ("PUBLIC_TO_EVERYONE", "SELF_ONLY") if p in options] or ["SELF_ONLY"]
    init, used = None, ""
    for privacy in order:
        try:
            init, used = _init(token, title, len(data), privacy), privacy
            break
        except TikTokError as e:
            if e.code != UNAUDITED or privacy == order[-1]:
                raise
    if not (init and init.get("publish_id") and init.get("upload_url")):
        raise TikTokError("TikTok init returned no publish_id or upload_url")
    _put(init["upload_url"], data)
    s = status(token, init["publish_id"], wait)
    return {"publish_id": init["publish_id"], "privacy": used, "status": s.get("status", "UNKNOWN"),
            "fail_reason": s.get("fail_reason", "")}


def authorize_url(client_key: str, state: str) -> str:
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_key": client_key, "response_type": "code", "scope": SCOPES,
        "redirect_uri": REDIRECT_URI, "state": state,
        "disable_auto_auth": "1"})   # always show the approval screen, even for an account that approved before


def code_from(pasted: str, state: str) -> str:
    """The authorization code from the address you land on (or the bare code). Checks the state when present."""
    pasted = pasted.strip()
    if "code=" not in pasted:
        return pasted
    q = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)   # also URL-decodes, as TikTok requires
    if q.get("state", [state])[0] != state:
        raise TikTokError("The address came from a different sign-in attempt. Run the command again.")
    if "error" in q:
        raise TikTokError(f"TikTok refused: {q['error'][0]}")
    return q["code"][0]


def auth(demo: bool = False) -> None:
    """Sign in once; prints the refresh token to save as TIKTOK_REFRESH_TOKEN.
    With demo=True (for the screen recording TikTok's review asks for) the token is never printed."""
    key, secret = os.environ.get("TIKTOK_CLIENT_KEY"), os.environ.get("TIKTOK_CLIENT_SECRET")
    if not (key and secret):
        sys.exit("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET first.")
    state = secrets.token_urlsafe(12)
    print("Open this link, sign in as the TikTok account and approve:\n\n" + authorize_url(key, state))
    print("\nYou will land on the Kenya On Record site. Copy the whole address from the browser bar and paste it here.")
    try:
        code = code_from(input("\nAddress: "), state)
        r = _token_call({"client_key": key, "client_secret": secret, "code": code,
                         "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI})
    except TikTokError as e:
        sys.exit(str(e))
    if demo:
        print(f"\nSigned in. Granted: {r.get('scope')}\n(Demo mode: the token is not shown or saved.)")
        return
    print(f"\nSigned in. Granted: {r.get('scope')}\nSave this as the GitHub secret TIKTOK_REFRESH_TOKEN:\n{r['refresh_token']}")


if __name__ == "__main__":
    args = sys.argv[1:]
    auth(demo="--demo" in args) if args[:1] == ["auth"] else sys.exit("usage: python tiktok.py auth [--demo]")
