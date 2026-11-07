"""TikTok upload: request shapes, the private fallback and the never-fatal hook (no network)."""
import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

for _k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"):
    os.environ.pop(_k, None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline  # noqa: E402
import tiktok  # noqa: E402

KEYS = {"TIKTOK_CLIENT_KEY": "k", "TIKTOK_CLIENT_SECRET": "s", "TIKTOK_REFRESH_TOKEN": "r"}


def ok(data=None):
    return 200, {}, json.dumps({"data": data or {}, "error": {"code": "ok", "message": ""}}).encode()


def err(code, status=200):
    return status, {}, json.dumps({"data": {}, "error": {"code": code, "message": "m"}}).encode()


class Fake:
    """Stands in for tiktok._request and records every call."""
    def __init__(self, init_results, options=("PUBLIC_TO_EVERYONE", "SELF_ONLY"), final="PUBLISH_COMPLETE"):
        self.calls, self.init_results, self.options, self.final = [], list(init_results), list(options), final

    def __call__(self, url, *, data=None, headers=None, method="POST", timeout=60):
        self.calls.append((url, data, headers or {}, method))
        if url.endswith("/oauth/token/"):
            return 200, {}, json.dumps({"access_token": "A", "refresh_token": "r"}).encode()
        if url.endswith("/creator_info/query/"):
            return ok({"creator_username": "kenyaonrecord", "privacy_level_options": self.options})
        if url.endswith("/video/init/"):
            return self.init_results.pop(0)
        if url.endswith("/status/fetch/"):
            return ok({"status": self.final})
        if method == "PUT":
            return 201, {}, b""
        raise AssertionError(url)


class Plan(unittest.TestCase):
    def test_small_file_is_one_chunk(self):
        self.assertEqual(tiktok.chunks(10_000_000), [(0, 9_999_999)])
        self.assertEqual(tiktok.chunks(64 * 1024 * 1024), [(0, 64 * 1024 * 1024 - 1)])

    def test_large_file_merges_the_remainder_into_the_last_chunk(self):
        size = 100 * 1024 * 1024 + 123
        plan = tiktok.chunks(size)
        self.assertEqual(len(plan), size // tiktok.CHUNK)
        self.assertEqual(plan[0], (0, tiktok.CHUNK - 1))
        self.assertEqual(plan[-1][1], size - 1)
        self.assertEqual(sum(hi - lo + 1 for lo, hi in plan), size)
        self.assertTrue(all(plan[i][1] + 1 == plan[i + 1][0] for i in range(len(plan) - 1)))

    def test_ready_needs_all_three(self):
        self.assertFalse(tiktok.ready())
        with mock.patch.dict(os.environ, KEYS):
            self.assertTrue(tiktok.ready())
        with mock.patch.dict(os.environ, {k: v for k, v in KEYS.items() if k != "TIKTOK_REFRESH_TOKEN"}):
            self.assertFalse(tiktok.ready())


class SignIn(unittest.TestCase):
    def test_authorize_url_carries_the_registered_redirect_and_scopes(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(tiktok.authorize_url("KEY", "st")).query)
        self.assertEqual(q["client_key"], ["KEY"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["scope"], ["user.info.basic,video.publish"])
        self.assertEqual(q["redirect_uri"], ["https://james84-bot.github.io/juakesho/"])
        self.assertEqual(q["state"], ["st"])
        self.assertEqual(q["disable_auto_auth"], ["1"])

    def test_code_from_rejects_address_without_code(self):
        with self.assertRaises(tiktok.TikTokError):
            tiktok.code_from(tiktok.authorize_url("key", "st"), "st")

    def test_code_from_decodes_and_checks_state(self):
        url = "https://james84-bot.github.io/juakesho/?code=ab%2Acd%21&scopes=x&state=st"
        self.assertEqual(tiktok.code_from(url, "st"), "ab*cd!")
        self.assertEqual(tiktok.code_from("plaincode", "st"), "plaincode")
        with self.assertRaises(tiktok.TikTokError):
            tiktok.code_from(url, "other")
        with self.assertRaises(tiktok.TikTokError):
            tiktok.code_from("https://x/?error=access_denied&code=1&state=st", "st")

    def test_refresh_sends_form_fields(self):
        f = Fake([])
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(tiktok, "_request", f):
            self.assertEqual(tiktok.access_token(), "A")
        url, data, headers, _ = f.calls[0]
        self.assertEqual(headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(urllib.parse.parse_qs(data.decode()), {"client_key": ["k"], "client_secret": ["s"],
                                                                  "grant_type": ["refresh_token"], "refresh_token": ["r"]})


class Upload(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.video = Path(self.dir.name) / "v.mp4"
        self.video.write_bytes(b"x" * 1000)

    def tearDown(self):
        self.dir.cleanup()

    def run_upload(self, fake):
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(tiktok, "_request", fake):
            return tiktok.upload(self.video, "Title #tag", wait=0)

    def test_public_when_accepted(self):
        f = Fake([ok({"publish_id": "p1", "upload_url": "https://up/x"})])
        res = self.run_upload(f)
        self.assertEqual(res, {"publish_id": "p1", "privacy": "PUBLIC_TO_EVERYONE", "status": "PUBLISH_COMPLETE", "fail_reason": ""})
        init = next(c for c in f.calls if c[0].endswith("/video/init/"))
        body = json.loads(init[1])
        self.assertEqual(body["source_info"], {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1})
        self.assertEqual(body["post_info"]["title"], "Title #tag")
        self.assertIs(body["post_info"]["is_aigc"], False)
        put = next(c for c in f.calls if c[3] == "PUT")
        self.assertEqual(put[0], "https://up/x")
        self.assertEqual(put[2]["Content-Range"], "bytes 0-999/1000")
        self.assertEqual(put[2]["Content-Length"], "1000")
        self.assertEqual(len(put[1]), 1000)

    def test_falls_back_to_private_when_unaudited(self):
        f = Fake([err("unaudited_client_can_only_post_to_private_accounts", 403),
                  ok({"publish_id": "p2", "upload_url": "https://up/y"})])
        res = self.run_upload(f)
        self.assertEqual(res["privacy"], "SELF_ONLY")
        levels = [json.loads(c[1])["post_info"]["privacy_level"] for c in f.calls if c[0].endswith("/video/init/")]
        self.assertEqual(levels, ["PUBLIC_TO_EVERYONE", "SELF_ONLY"])

    def test_other_errors_are_not_swallowed(self):
        f = Fake([err("spam_risk_too_many_posts")])
        with self.assertRaises(tiktok.TikTokError) as c:
            self.run_upload(f)
        self.assertEqual(c.exception.code, "spam_risk_too_many_posts")
        self.assertFalse(any(c[3] == "PUT" for c in f.calls))

    def test_only_private_offered_goes_straight_to_private(self):
        f = Fake([ok({"publish_id": "p3", "upload_url": "https://up/z"})], options=["SELF_ONLY"])
        self.assertEqual(self.run_upload(f)["privacy"], "SELF_ONLY")
        self.assertEqual(sum(c[0].endswith("/video/init/") for c in f.calls), 1)

    def test_failed_status_is_reported(self):
        f = Fake([ok({"publish_id": "p4", "upload_url": "https://up/w"})], final="FAILED")
        self.assertEqual(self.run_upload(f)["status"], "FAILED")


class Hook(unittest.TestCase):
    post = {"id": "p", "reel": True, "beats": ["A line."], "message": "A line."}

    def test_skipped_without_secrets_or_for_stills(self):
        self.assertFalse(pipeline._tiktok_post("W", dict(self.post)))
        with mock.patch.dict(os.environ, KEYS):
            self.assertFalse(pipeline._tiktok_post("W", {"id": "p", "reel": False}))

    def test_public_post_returns_true_and_private_returns_false(self):
        for privacy, expect in (("PUBLIC_TO_EVERYONE", True), ("SELF_ONLY", False)):
            p = dict(self.post)
            res = {"publish_id": "id9", "privacy": privacy, "status": "PUBLISH_COMPLETE", "fail_reason": ""}
            with mock.patch.dict(os.environ, KEYS), mock.patch.object(tiktok, "upload", return_value=res), \
                    mock.patch.object(pipeline, "_notify") as n:
                self.assertIs(pipeline._tiktok_post("W", p), expect)
            self.assertEqual(p["tt_id"], "id9")
            self.assertEqual(n.called, not expect)

    def test_never_fatal(self):
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(tiktok, "upload", side_effect=RuntimeError("boom")), \
                mock.patch.object(pipeline, "_notify") as n:
            self.assertFalse(pipeline._tiktok_post("W", dict(self.post)))
        self.assertIn("boom", n.call_args[0][0])


class Commands(unittest.TestCase):
    def test_tiktokcheck_reports_missing_keys_and_success(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline._main(["tiktokcheck", "--dry-run"]), 1)
            with mock.patch.dict(os.environ, KEYS), mock.patch.object(tiktok, "check", return_value="kenyaonrecord"):
                self.assertNotEqual(pipeline._main(["tiktokcheck", "--dry-run"]), 1)
            with mock.patch.dict(os.environ, KEYS), mock.patch.object(tiktok, "check", side_effect=tiktok.TikTokError("bad")):
                self.assertEqual(pipeline._main(["tiktokcheck", "--dry-run"]), 1)

    def test_tiktoksend_posts_the_latest_published_reel(self):
        import contextlib
        import io
        seen = []
        def fake(label, post):
            seen.append((label, post["id"]))
            post["tt_id"] = "x"
            return False
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(pipeline, "_tiktok_post", fake):
            self.assertNotEqual(pipeline._main(["tiktoksend"]), 1)
        self.assertEqual(len(seen), 1)


class AuthDemo(unittest.TestCase):
    def run_auth(self, demo):
        import contextlib
        import io
        out = io.StringIO()
        pasted = "https://james84-bot.github.io/juakesho/?code=abc&state=ST"
        with mock.patch.dict(os.environ, KEYS), mock.patch.object(tiktok.secrets, "token_urlsafe", return_value="ST"), \
                mock.patch("builtins.input", return_value=pasted), \
                mock.patch.object(tiktok, "_token_call", return_value={"refresh_token": "SECRET-RT", "scope": "a,b"}), \
                contextlib.redirect_stdout(out):
            tiktok.auth(demo=demo)
        return out.getvalue()

    def test_token_is_printed_normally_and_hidden_in_demo(self):
        self.assertIn("SECRET-RT", self.run_auth(False))
        shown = self.run_auth(True)
        self.assertNotIn("SECRET-RT", shown)
        self.assertIn("Demo mode", shown)


if __name__ == "__main__":
    unittest.main()
