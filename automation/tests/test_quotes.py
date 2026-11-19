"""People's exact words: quotes come from the report itself (never the model), a post may carry only a run of a
speaker's words exactly as printed, and a quote line gets the room and the look of a quote."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import draft  # noqa: E402
import guard  # noqa: E402
import quotes  # noqa: E402

PAGE = """<html><body><article>
<p>Members of Parliament on Tuesday removed the Sh100 million fine from the Local Content Bill.</p>
<p>&ldquo;We will not allow foreign firms to exploit our workers any more,&rdquo; Trade CS Lee Kinyanjui said on Tuesday.</p>
<p>Speaking in Nairobi, President William Ruto said: &ldquo;Every Kenyan deserves a decent job and fair pay.&rdquo;</p>
<p>&ldquo;The bill was passed in a hurry without public participation,&rdquo; said Kikuyu MP Kimani Ichung&rsquo;wah.</p>
<p>&ldquo;This is totally unacceptable to all of us,&rdquo; he said.</p>
<p>The <a href="/x">"Finance Bill"</a> was tabled yesterday.</p>
</article></body></html>"""

POST = {"id": "2026-w47-hot-1119", "template": "sauti", "hot": True, "caption": "x",
        "beats": ["MPs removed a *Sh100 million* fine on firms ignoring Kenyan workers.",
                  "The revised Local Content Bill also dropped jail terms for bosses.",
                  "Has a foreign firm ever denied you a local job?"],
        "source_links": [{"outlet": "Capital FM", "link": "https://www.capitalfm.co.ke/news/x", "title": "t"}]}


class Extract(unittest.TestCase):
    def test_quotes_with_a_named_speaker_only(self):
        got = quotes.from_text(quotes.paragraphs(PAGE))
        self.assertEqual([(q["speaker"], q["text"]) for q in got], [
            ("Trade CS Lee Kinyanjui", "We will not allow foreign firms to exploit our workers any more"),
            ("President William Ruto", "Every Kenyan deserves a decent job and fair pay."),
            ("Kikuyu MP Kimani Ichung’wah", "The bill was passed in a hurry without public participation"),
        ])   # "he said" names nobody, and "Finance Bill" is a name, not a quote

    def test_exact_words_pass_and_reworded_ones_fail(self):
        found = quotes.from_text(quotes.paragraphs(PAGE))
        self.assertEqual(quotes.problem("Ruto: “Every Kenyan deserves a decent job”", found), "")       # a run of words
        self.assertIn("not word for word", quotes.problem("Ruto: “Every Kenyan deserves a good job”", found))
        self.assertIn("ellipsis", quotes.problem("Ruto: “Every Kenyan … fair pay”", found))
        self.assertIn("no quote was found", quotes.problem('He said "we are tired of this"', []))
        self.assertEqual(quotes.problem('The "Finance Bill" was tabled.', []), "")   # under 3 words: a name


class Guard(unittest.TestCase):
    def post(self, beats, found):
        return {**POST, "beats": beats, "quotes": found}

    def test_a_quote_line_gets_room_but_must_be_exact(self):
        found = quotes.from_text(quotes.paragraphs(PAGE))
        ok = guard.check(self.post([POST["beats"][0],
                                    "Kikuyu MP Kimani Ichung’wah: “The bill was passed in a hurry without public participation”",
                                    POST["beats"][2]], found))
        self.assertFalse([e for e in ok.errors if "quote" in e or "too long" in e or "beats[1]" in e], ok.errors)
        bad = guard.check(self.post([POST["beats"][0], "Ruto: “Every Kenyan deserves good jobs and fair pay”",
                                     POST["beats"][2]], found))
        self.assertTrue(any(e.startswith("quote:") for e in bad.errors), bad.errors)

    def test_an_invented_quote_fails_even_without_collected_quotes(self):
        rep = guard.check(self.post([POST["beats"][0], "MPs said “we have protected Kenyan jobs today”.", POST["beats"][2]], []))
        self.assertTrue(any(e.startswith("quote:") for e in rep.errors), rep.errors)


class Voices(unittest.TestCase):
    def test_the_writer_puts_one_exact_quote_in(self):
        def call(system, user, max_tokens=0):
            self.assertIn("Trade CS Lee Kinyanjui (Capital FM): “We will not allow", user)
            return json.dumps({"quote_used": True, "beats": [
                POST["beats"][0], "CS Lee Kinyanjui: “We will not allow foreign firms to exploit our workers”", POST["beats"][2]]})
        post = json.loads(json.dumps(POST))
        out = draft.add_voices([post], get=lambda url: PAGE.encode(), call=call)[0]
        self.assertEqual(out["beats"][1], "CS Lee Kinyanjui: “We will not allow foreign firms to exploit our workers”")
        self.assertEqual(len(out["quotes"]), 3)

    def test_a_reworded_quote_is_dropped_and_the_script_stands(self):
        def call(system, user, max_tokens=0):
            return json.dumps({"quote_used": True, "beats": [
                POST["beats"][0], "Kinyanjui: “Foreign firms will no longer exploit our workers”", POST["beats"][2]]})
        post = json.loads(json.dumps(POST))
        out = draft.add_voices([post], get=lambda url: PAGE.encode(), call=call)[0]
        self.assertEqual(out["beats"], POST["beats"])

    def test_no_quotes_in_the_reports_no_call(self):
        def call(*a, **k):
            raise AssertionError("no quotes: the writer is not asked")
        post = json.loads(json.dumps(POST))
        out = draft.add_voices([post], get=lambda url: b"<p>Nothing quoted in this report at all, only facts.</p>", call=call)[0]
        self.assertEqual(out["quotes"], [])


if __name__ == "__main__":
    unittest.main()
