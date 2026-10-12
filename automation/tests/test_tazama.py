"""Tazama Hii: clip rights, intake, window caps, captions and the guard (no network, no rendering)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard  # noqa: E402
import tazama  # noqa: E402

NOW = dt.datetime(2026, 10, 12, 20, tzinfo=dt.timezone(dt.timedelta(hours=3)))


class Tazama(unittest.TestCase):
    def test_caption_must_say_where_the_clip_came_from(self):
        self.assertEqual(tazama.parse_caption("ruhusa @kevo254 DM 12 Oct\nMCA road promise")["rights"], "permission")
        self.assertEqual(tazama.parse_caption("yangu\nwe filmed the queue")["credit"], "Jua Kesho")
        q = tazama.parse_caption("nukuu Citizen TV https://youtu.be/x\nCS on teargas")
        self.assertEqual((q["rights"], q["credit"], q["source"]), ("quote", "Citizen TV", "https://youtu.be/x"))
        self.assertIsNone(tazama.parse_caption("check this out"))
        self.assertIsNone(tazama.parse_caption("ruhusa"))   # permission from whom?

    def test_intake(self):
        video = {"file_id": "F", "file_size": 5_000_000, "duration": 30}
        reply, clip = tazama.intake({"video": video, "caption": "hii ni moto"}, NOW)
        self.assertIsNone(clip)
        self.assertIn("FIRST line", reply)
        reply, clip = tazama.intake({"video": {**video, "file_size": 30_000_000}, "caption": "yangu"}, NOW)
        self.assertIsNone(clip)
        reply, clip = tazama.intake({"document": {**video, "mime_type": "video/mp4"}, "caption": "yangu\nqueue at Huduma"}, NOW)
        self.assertEqual((clip["status"], clip["rights"], clip["file_id"]), ("queued", "own", "F"))
        self.assertEqual(tazama.intake({"text": "hello"}, NOW), ("", None))

    def test_window_caps(self):
        self.assertEqual(tazama.window({"start": 3, "end": 30}, {"rights": "quote"}, 60), (3.0, 11.0))
        self.assertEqual(tazama.window({"start": 0, "end": 90}, {"rights": "permission"}, 60), (0.0, 40.0))
        self.assertEqual(tazama.window({"start": "x"}, {"rights": "own"}, 12), (0.0, 12.0))

    def test_captions_retimed_and_chunked(self):
        segs = [{"start": 2.0, "end": 6.0, "text": "one two three four five six seven eight"}, {"start": 20, "end": 22, "text": "late"}]
        caps = tazama.captions(segs, 2.0, 12.0)
        self.assertEqual([c["text"] for c in caps], ["one two three four five six seven", "eight"])
        self.assertEqual((caps[0]["start"], caps[1]["end"]), (0.0, 4.0))

    def test_box_even_and_inside_the_screen(self):
        for w, h in ((1280, 720), (720, 1280), (1080, 1080)):
            x, y, bw, bh = tazama.box({"w": w, "h": h})
            self.assertEqual((bw % 2, bh % 2), (0, 0))
            self.assertTrue(x >= 0 and bw <= 1080 and bh <= tazama.BOX_MAX_H and y + bh < 1700)

    def test_guard(self):
        post = {"id": "2026-w42-tazama-1", "template": "tazama", "headline": "Barabara *itajengwa kesho*",
                "credit": "@kevo254", "rights": "ruhusa @kevo254", "rights_kind": "permission",
                "hook": ["Watch what he promised."], "verdict": ["Same promise in *2022*.", "Kesho ni lini?"],
                "beats": ["Watch what he promised.", "Same promise in *2022*.", "Kesho ni lini?"],
                "caption": "c", "clip_window": [0, 20]}
        self.assertEqual(guard.check(post).errors, [])
        self.assertTrue(guard.check({**post, "rights_kind": ""}).errors)
        self.assertTrue(guard.check({**post, "rights_kind": "quote"}).errors)   # 20 s of news footage is too long


if __name__ == "__main__":
    unittest.main()
