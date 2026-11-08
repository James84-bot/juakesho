"""Outlet graphics: a picture a publisher already designed (a label, a headline, an inset) is never used as our photo.
The model's verdict is kept per picture; a check that cannot run never costs a post its photo."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft  # noqa: E402
import picture  # noqa: E402
import posted  # noqa: E402


def jpeg(colour=(120, 90, 60), size=(900, 600)) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, "JPEG")
    return buf.getvalue()


class OutletEdit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.checks = Path(self.tmp.name) / "photo_checks.json"
        self.patch = mock.patch.object(picture, "_checks_file", lambda: self.checks)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_an_edited_graphic_is_named_and_remembered(self):
        calls = []
        with mock.patch.object(draft, "look_at", lambda data, ask: calls.append(1) or
                               '```json\n{"edited": true, "what": "HEALTH label and an inset circle"}\n```'):
            self.assertEqual(picture.outlet_edit(jpeg()), "HEALTH label and an inset circle")
            self.assertEqual(picture.outlet_edit(jpeg()), "HEALTH label and an inset circle")   # from the file
        self.assertEqual(len(calls), 1)
        self.assertTrue(json.loads(self.checks.read_text())[next(iter(json.loads(self.checks.read_text())))]["edited"])

    def test_a_plain_photograph_passes(self):
        with mock.patch.object(draft, "look_at", lambda data, ask: '{"edited": false, "what": ""}'):
            self.assertEqual(picture.outlet_edit(jpeg((10, 20, 30))), "")

    def test_no_model_means_no_verdict_and_nothing_kept(self):
        def down(data, ask):
            raise RuntimeError("no model could look at the picture: no key set")
        with mock.patch.object(draft, "look_at", down):
            self.assertEqual(picture.outlet_edit(jpeg((1, 2, 3))), "")
        self.assertFalse(self.checks.exists())   # tried again next time

    def test_the_ask_keeps_text_that_is_part_of_the_scene(self):
        ask = " ".join(picture.EDIT_ASK.split())
        for words in ("name plates", "signs", "screens", "another picture inside", "logo", "headlines", "stage backdrops"):
            self.assertIn(words, ask)


class PhotoOfSkipsGraphics(unittest.TestCase):
    ITEM = {"link": "https://www.kenyans.co.ke/news/1-x", "outlet": "Kenyans.co.ke", "credit": "", "img": ""}

    def run_with(self, verdict):
        page = b'<meta property="og:image" content="https://cdn.example/x.jpg">'
        with mock.patch.object(posted, "_get", lambda url, timeout=20: page if "kenyans" in url else jpeg()), \
                mock.patch.object(picture, "outlet_edit", lambda data: verdict):
            return posted._photo_of(dict(self.ITEM))

    def test_an_outlet_graphic_is_not_used(self):
        self.assertIsNone(self.run_with("HEALTH label and an inset circle"))

    def test_a_photograph_is_used_with_its_credit(self):
        got = self.run_with("")
        self.assertIsNotNone(got)
        self.assertEqual(got[1]["credit"], "Photo: Kenyans.co.ke")


class LookAt(unittest.TestCase):
    """The picture goes to Gemini (free tier) as inline JPEG at temperature 0; Claude Haiku takes over when Gemini
    can't answer."""

    class Reply:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(self.body).encode()

    def test_gemini_first_then_claude(self):
        sent = []

        def fake(req, timeout=0):
            body = json.loads(req.data)
            sent.append((req.full_url, body))
            if "generativelanguage" in req.full_url:
                raise draft.urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"model error"))
            return self.Reply({"content": [{"type": "text", "text": '{"edited": false}'}], "usage": {}})

        env = {"GEMINI_API_KEY": "g", "ANTHROPIC_API_KEY": "a", "JUA_PROVIDER": ""}
        with mock.patch.dict(draft.os.environ, env), mock.patch.object(draft.urllib.request, "urlopen", fake), \
                mock.patch.dict(draft.SPEND, {"calls": 0, "usd": 0.0}), mock.patch.object(draft.time, "sleep", lambda s: None):
            self.assertEqual(draft.look_at(jpeg(size=(3000, 2000)), "edited?"), '{"edited": false}')
        gem, claude = sent[0][1], sent[-1][1]
        self.assertEqual(gem["generationConfig"]["temperature"], 0)
        self.assertEqual(gem["contents"][0]["parts"][0]["inlineData"]["mimeType"], "image/jpeg")
        self.assertEqual(claude["model"], draft.CRITIC_MODEL)
        self.assertEqual(claude["messages"][0]["content"][0]["type"], "image")
        from PIL import Image
        import base64
        small = Image.open(io.BytesIO(base64.b64decode(claude["messages"][0]["content"][0]["source"]["data"])))
        self.assertLessEqual(max(small.size), 1024)

    def test_no_key_raises(self):
        with mock.patch.dict(draft.os.environ, {"GEMINI_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                draft.look_at(jpeg(), "edited?")


if __name__ == "__main__":
    unittest.main()
