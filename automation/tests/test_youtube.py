"""YouTube Shorts upload: request shapes and the never-fatal hook (no network)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", *("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline  # noqa: E402
import youtube  # noqa: E402

KEYS = {"YT_CLIENT_ID": "i", "YT_CLIENT_SECRET": "s", "YT_REFRESH_TOKEN": "r"}


class Resp:
    def __init__(self, payload=b"", headers=None):
        self.payload, self.headers = payload, headers or {}

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Upload(unittest.TestCase):
    def test_ready_needs_all_three(self):
        self.assertFalse(youtube.ready())
        with mock.patch.dict(os.environ, KEYS):
            self.assertTrue(youtube.ready())
        with mock.patch.dict(os.environ, {k: v for k, v in KEYS.items() if k != "YT_REFRESH_TOKEN"}):
            self.assertFalse(youtube.ready())

    def test_body_limits_and_public(self):
        b = youtube.body("t" * 300, "d" * 9000)
        self.assertEqual(len(b["snippet"]["title"]), 100)
        self.assertLessEqual(len(b["snippet"]["description"]), 5000)
        self.assertEqual(b["status"]["privacyStatus"], "public")
        self.assertFalse(b["status"]["selfDeclaredMadeForKids"])

    def test_upload_flow(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, KEYS):
            mp4 = Path(d) / "a.mp4"
            mp4.write_bytes(b"video")
            seen = []

            def fake(req, timeout=0):
                seen.append((req.method, req.full_url))
                if "oauth2" in req.full_url:
                    return Resp(json.dumps({"access_token": "tok"}).encode())
                if req.method == "POST":
                    return Resp(headers={"Location": "https://upload.example/session"})
                self.assertEqual(req.data, b"video")
                return Resp(json.dumps({"id": "abc", "status": {"privacyStatus": "private"}}).encode())
            with mock.patch("urllib.request.urlopen", fake):
                res = youtube.upload(mp4, "Title #Shorts", "desc")
        self.assertEqual(res, {"id": "abc", "privacy": "private"})
        self.assertEqual([m for m, _ in seen], ["POST", "POST", "PUT"])

    def test_bad_refresh_token_is_an_error(self):
        with mock.patch.dict(os.environ, KEYS), \
             mock.patch.object(youtube, "_post", return_value={"error": "invalid_grant"}):
            with self.assertRaises(RuntimeError):
                youtube.access_token()

    def test_check_reads_the_channel_name_and_uploads_nothing(self):
        seen = []

        def fake(req, timeout=0):
            seen.append((req.get_method(), req.full_url))
            return Resp(json.dumps({"items": [{"snippet": {"title": "Kenya on Record"}}]}).encode())
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(youtube, "access_token", return_value="tok"), \
             mock.patch("urllib.request.urlopen", fake):
            self.assertEqual(youtube.check(), "Kenya on Record")
        self.assertEqual(seen, [("GET", "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true")])

    def test_check_fails_clearly_when_the_account_has_no_channel(self):
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(youtube, "access_token", return_value="tok"), \
             mock.patch("urllib.request.urlopen", lambda req, timeout=0: Resp(b"{}")):
            with self.assertRaises(RuntimeError):
                youtube.check()

    def test_the_youtubecheck_command_reports_missing_keys_and_success(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):   # keep test output off the run page's annotations
            with mock.patch.dict(os.environ, {}, clear=False):
                for k in KEYS:
                    os.environ.pop(k, None)
                self.assertEqual(pipeline._main(["youtubecheck", "--dry-run"]), 1)
            with mock.patch.dict(os.environ, KEYS), mock.patch.object(youtube, "check", return_value="Kenya on Record"):
                self.assertNotEqual(pipeline._main(["youtubecheck", "--dry-run"]), 1)


class Hook(unittest.TestCase):
    post = {"id": "p1", "reel": True, "beats": ["A line"], "caption": "cap #KenyaOnRecord"}

    def test_skipped_without_keys_or_reel(self):
        with mock.patch.object(youtube, "upload") as up:
            pipeline._youtube_short("W", dict(self.post))
            with mock.patch.dict(os.environ, KEYS):
                pipeline._youtube_short("W", {"id": "x", "beats": ["a"]})
        up.assert_not_called()

    def test_failure_is_reported_not_raised(self):
        p = dict(self.post)
        with mock.patch.dict(os.environ, KEYS), \
             mock.patch.object(youtube, "upload", side_effect=RuntimeError("quota")), \
             mock.patch.object(pipeline, "_notify") as note:
            pipeline._youtube_short("W", p)
        self.assertNotIn("yt_id", p)
        self.assertIn("failed", note.call_args[0][0])

    def test_success_records_id_and_flags_private(self):
        p = dict(self.post)
        with mock.patch.dict(os.environ, KEYS), \
             mock.patch.object(youtube, "upload", return_value={"id": "abc", "privacy": "private"}), \
             mock.patch.object(pipeline, "_notify") as note:
            pipeline._youtube_short("W", p)
        self.assertEqual(p["yt_id"], "abc")
        self.assertIn("private", note.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
