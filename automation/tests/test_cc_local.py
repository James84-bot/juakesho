"""cc_local: licence check and the Tazama caption (no network)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cc_local  # noqa: E402
import tazama  # noqa: E402


def _api(lic):
    return lambda url: json.dumps({"items": [{"snippet": {"channelTitle": "Wild Springs Adventures", "title": "Aberdares"},
                                              "status": {"license": lic}}]}).encode()


class CCLocal(unittest.TestCase):
    def test_video_id(self):
        self.assertEqual(cc_local.video_id("https://www.youtube.com/watch?v=abc123&t=5"), "abc123")
        self.assertEqual(cc_local.video_id("https://youtu.be/abc123"), "abc123")

    def test_only_creative_commons_passes(self):
        info = cc_local.check_licence("abc", "k", _api("creativeCommon"))
        self.assertEqual(info["channel"], "Wild Springs Adventures")
        with self.assertRaises(ValueError):
            cc_local.check_licence("abc", "k", _api("youtube"))

    def test_caption_is_a_valid_tazama_permission_line(self):
        info = cc_local.check_licence("abc", "k", _api("creativeCommon"))
        parsed = tazama.parse_caption(cc_local.caption(info, "A waterfall in the Aberdares"))
        self.assertEqual(parsed["rights"], "permission")
        self.assertIn("Wild Springs Adventures", parsed["credit"])
        self.assertEqual(parsed["source"], "https://www.youtube.com/watch?v=abc")
        self.assertIn("waterfall", parsed["note"])


if __name__ == "__main__":
    unittest.main()
