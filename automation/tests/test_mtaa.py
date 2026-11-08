"""Mtaa Mode: the music chart is YouTube's numbers, ranked and labelled the way the post says; the animated scenes
are fiction that keeps to the street rules (no politics, tribe, religion as the target, vices or real people), pass
an editor, and play on one shared timeline (animation, bubbles, sound). Rendered for real under the brand, the still
frame is clean and the cast is on stage."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402
import mtaa  # noqa: E402

NOW = dt.datetime(2026, 11, 8, 12, 40, tzinfo=mtaa.EAT)
# YouTube's most-popular music list for Kenya as the runner read it on 8 Nov 2026 (title, channel, views, published)
REAL = [("BIEN - I’ll Be Okay (Official Music Video)", "Bien", 11394907, "2026-10-09"),
        ("Kapitani x Toxic Lyrikali - SHING (Official Music Video)", "Kapitani", 3048623, "2026-10-13"),
        ("Otile Brown x  Darassa - KWA NEEMA (Official Video)", "Otile Brown Official", 1326476, "2026-10-23"),
        ("Zzero Sufuri   Otero Ft  Toxic Lyrikali (Official Music Video)", "zzero sufuri", 1898527, "2026-10-13"),
        ("Zuchu ft Diamond Platnumz - Mvua Ya Baraka ( Lyric Audio)", "Zuchu", 1700306, "2026-10-30"),
        ("Ywaya Tajiri - Somebody's Daughter", "Ywaya Tajiri", 767465, "2026-10-23"),
        ("Toxic Lyrikali - Mafia Boss (Lyric Video)", "Toxic Lyrikali", 287452, "2026-10-30"),
        ("ALEX KASAU KATOMBI-GOSPEL(OFFICIAL AUDIO)", "Alex Kasau Katombi", 166155, "2026-11-06"),
        ("NIWA YIULU - WILBERFORCE MUSYOKA (OFFICIAL VIDEO)", "Wilberforce Musyoka Official", 718698, "2026-10-21"),
        ("Kapitani - More (Official Visualizer)", "Kapitani", 424799, "2026-10-23"),
        ("Victony - SLICK Remix (feat. Don Toliver & Summer Walker) [Official Music Video]", "Victony", 6219249, "2026-10-16"),
        ("COLLOBLUE FT RAYBEAST -  STINGO GANI (Official music video)", "Colloblue ", 429564, "2026-10-22")]


def items(rows):
    return {"items": [{"id": f"v{i}", "snippet": {"title": t, "channelTitle": c, "publishedAt": d + "T12:00:00Z"},
                       "statistics": {"viewCount": str(v)}} for i, (t, c, v, d) in enumerate(rows)]}


def scene(**over):
    p = {"id": "2026-w46-mon-1245", "template": "scene", "publish_at": "2026-11-09T12:45:00+03:00", "size": "story",
         "bg": "usiku", "title": "Tarehe 5 kwa ploti", "place": "plot", "cast": ["brayo", "landlord"],
         "lines": [{"who": "landlord", "text": "Brayo! Leo ni tarehe tano.", "do": "walk_in", "face": "happy"},
                   {"who": "landlord", "text": "Nimekuja kwa ile kitu yangu.", "do": "knock", "face": "smug"},
                   {"who": "brayo", "text": "Mzee, nilikuwa nakuja kukuletea right now.", "do": "beg", "face": "happy"},
                   {"who": "landlord", "text": "Ulisema hivyo mwezi jana.", "do": "cross", "face": "angry"},
                   {"who": "brayo", "text": "Na nilikuwa na nia safi mwezi jana pia.", "do": "shrug", "react": "angry"},
                   {"who": "landlord", "text": "Nia safi hailipi rent, Brayo.", "do": "point", "face": "angry", "react": "shock"}],
         "caption": "Rent day at the plot. Who is your Brayo?\n\nAnimated skit: characters are fictional.\n\n#MtaaMode #Nairobi"}
    p.update(over)
    return p


class Titles(unittest.TestCase):
    def test_real_titles_read_as_artist_and_song(self):
        want = [("Bien", "I’ll Be Okay"), ("Kapitani x Toxic Lyrikali", "Shing"), ("Otile Brown x Darassa", "Kwa Neema"),
                ("Zzero Sufuri ft Toxic Lyrikali", "Otero"), ("Zuchu ft Diamond Platnumz", "Mvua Ya Baraka"),
                ("Ywaya Tajiri", "Somebody's Daughter"), ("Toxic Lyrikali", "Mafia Boss"), ("Alex Kasau Katombi", "Gospel"),
                ("Wilberforce Musyoka", "Niwa Yiulu"), ("Kapitani", "More"),
                ("Victony ft Don Toliver & Summer Walker", "SLICK Remix"), ("Colloblue ft Raybeast", "Stingo Gani")]
        self.assertEqual([mtaa.split_title(t, c) for t, c, _, _ in REAL], want)


    def test_long_artist_lists_are_never_cut_into_the_song(self):
        long = "Diamond Platnumz Ft Focalistic, Uncool MC, Ruff Kid, Xduppy & Dj Maphorisa"
        self.assertEqual(mtaa.split_title(long + " - Song Name (Official Video)", "Diamond Platnumz"),
                         ("Diamond Platnumz ft Focalistic, Uncool MC, Ruff Kid, Xduppy & Dj Maphorisa", "Song Name"))
        artist, song = mtaa.split_title(long + " (Official Video)", "Diamond Platnumz")   # no song name in the title
        self.assertEqual(artist, "Diamond Platnumz")
        self.assertTrue(song.startswith("Diamond Platnumz Ft Focalistic"))   # the title as written
        self.assertEqual(mtaa.split_title("Megan Thee Stallion - Thin Ice - Tina Tuesday Freestyle", "Megan Thee Stallion"),
                         ("Megan Thee Stallion", "Thin Ice - Tina Tuesday Freestyle"))


class Chart(unittest.TestCase):
    def songs(self, rows=REAL, **kw):
        return mtaa.chart_songs(key="k", now=NOW, get=lambda url: json.dumps(items(rows)), **kw)

    def test_ranked_by_views_a_day_and_dated(self):
        songs, as_of = self.songs()
        self.assertEqual(as_of, "8 Nov 2026, 12:40 EAT")
        self.assertEqual(len(songs), 10)
        per_day = [s["per_day"] for s in songs]
        self.assertEqual(per_day, sorted(per_day, reverse=True))
        self.assertEqual(songs[0]["artist"], "Bien")   # 11.39M views in 30 days: about 381K a day
        days = (NOW - dt.datetime(2026, 10, 9, 12, 0, tzinfo=dt.timezone.utc)).total_seconds() / 86400
        self.assertEqual(songs[0]["per_day"], round(11394907 / days))

    def test_old_unreadable_and_uncounted_videos_are_left_out(self):
        rows = REAL[:6] + [("Old hit - Song", "Old", 9 ** 9, "2025-01-01"), ("مين اللي سرق", "X", 9 ** 9, "2026-11-01")]
        data = items(rows)
        data["items"].append({"id": "nov", "snippet": {"title": "A - B", "channelTitle": "A", "publishedAt": "2026-11-01T00:00:00Z"},
                              "statistics": {}})
        songs, _ = mtaa.chart_songs(key="k", now=NOW, get=lambda url: json.dumps(data))
        self.assertEqual(len(songs), 6)
        self.assertFalse({"Old", "X", "A"} & {s["artist"] for s in songs})

    def test_no_key_no_chart(self):
        with mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                mtaa.chart_songs(now=NOW, get=lambda url: "{}")

    def test_post_says_how_it_was_ranked_and_passes_the_guard(self):
        songs, as_of = self.songs()
        p = mtaa.chart_post({"id": "2026-w46-mon-1730", "template": "chart", "publish_at": "2026-11-09T17:30:00+03:00"},
                            songs, as_of)
        self.assertIn("Ranked by views per day since release", p["caption"])
        self.assertIn(as_of, p["caption"])
        self.assertLessEqual(p["caption"].count("#"), 3)
        self.assertEqual(p["songs"][0]["per_day_text"], "381K")
        self.assertEqual(guard.check(p).errors, [])
        self.assertEqual(mtaa.auto_problem(p), "")

    def test_a_down_api_holds_the_chart_and_never_writes_around_it(self):
        def down(url):
            raise OSError("timeout")
        slot = {"id": "c", "template": "chart", "publish_at": "2026-11-09T17:30:00+03:00"}
        with mock.patch.dict(os.environ, {"YOUTUBE_API_KEY": "k"}):
            posts, held = mtaa.draft([slot], get=down, now=NOW)
        self.assertEqual(posts, [])
        self.assertIn("could not be read", held[0][1])

    def test_long_names_are_shortened_on_the_row_and_kept_whole_in_the_caption(self):
        long = "Diamond Platnumz, Xduppy & Dj Maphorisa ft Focalistic, Uncool MC, Ricky & Angekebabuye"
        self.assertEqual(mtaa.fit(long, mtaa.ROW_ARTIST), "Diamond Platnumz, Xduppy & Dj Maphorisa\u2026")
        self.assertEqual(mtaa.fit("Bien", mtaa.ROW_ARTIST), "Bien")
        songs, as_of = self.songs()
        songs[0]["artist"] = long
        p = mtaa.chart_post({"id": "c", "template": "chart", "publish_at": "2026-11-09T17:30:00+03:00"}, songs, as_of)
        self.assertLessEqual(len(p["songs"][0]["artist_row"]), mtaa.ROW_ARTIST)
        self.assertIn(long, p["caption"])

    def test_rows_land_from_ten_up_to_one(self):
        tl = mtaa.chart_timeline(10)
        self.assertEqual(tl["rows"], sorted(tl["rows"], reverse=True))   # #1 (index 0) lands last
        self.assertGreater(tl["top"], max(tl["rows"]))
        self.assertGreater(tl["end"], tl["top"] + 3)


class Timing(unittest.TestCase):
    def test_lines_follow_each_other_and_the_punchline_is_last(self):
        tl = mtaa.scene_timeline(scene())
        lines = tl["lines"]
        self.assertLess(lines[0]["start"], 1.0)   # the walk-in talks as it arrives: no dead air
        for a, b in zip(lines, lines[1:]):
            self.assertGreater(b["start"], a["end"])
            self.assertLess(a["start"], a["talk_end"])
            self.assertLessEqual(a["talk_end"], a["end"])
        self.assertEqual(tl["punch"], {"who": "landlord", "at": lines[-1]["start"]})
        self.assertGreater(tl["end"], lines[-1]["end"])
        self.assertLess(tl["end"], 35)
        self.assertEqual(mtaa.duration(scene()), tl["end"])

    def test_who_walks_in_and_where_they_stand(self):
        tl = mtaa.scene_timeline(scene())
        brayo, landlord = tl["cast"]
        self.assertIsNone(brayo["enter"])
        self.assertLessEqual(landlord["enter"], tl["lines"][0]["start"])
        self.assertEqual((brayo["x"], landlord["x"]), (300, 780))
        self.assertGreater(landlord["x"] + landlord["walk"], 1080 + 100)   # starts past the frame's edge
        self.assertEqual([a["do"] for a in landlord["acts"]], ["knock", "cross", "point"])

    def test_still_frame_is_the_hook_never_the_punchline(self):
        tl = mtaa.scene_timeline(scene())
        still = mtaa.still_time(scene())
        self.assertGreater(still, tl["lines"][0]["talk_end"])
        self.assertLess(still, tl["lines"][1]["start"])

    def test_matatu_seats_everyone_and_no_one_walks_out_of_the_frame_on_the_cut(self):
        tl = mtaa.scene_timeline(scene(place="matatu", lines=[dict(l, do="none") for l in scene()["lines"]]))
        self.assertTrue(all(c["seated"] for c in tl["cast"]))
        lines = scene()["lines"][:-1] + [dict(scene()["lines"][-1], do="walk_out")]
        self.assertIsNone(mtaa.scene_timeline(scene(lines=lines))["punch"])

    def test_sound_follows_what_happens(self):
        cues = mtaa.cues(scene())
        kinds = [k for _, k in cues]
        self.assertEqual(kinds[0], "steps")           # the landlord walks in
        self.assertIn("knock", kinds)
        self.assertEqual(kinds[-1], "hit")            # the punchline lands
        self.assertEqual([t for t, _ in cues], sorted(t for t, _ in cues))


class StreetRules(unittest.TestCase):
    def errors(self, **over):
        return mtaa.check(scene(**over))[0]

    def line(self, text, **more):
        lines = scene()["lines"]
        lines[2] = {"who": "brayo", "text": text, "do": "none", **more}
        return self.errors(lines=lines)

    def test_a_clean_scene_passes_both_checks(self):
        self.assertEqual(self.errors(), [])
        self.assertEqual(guard.check(scene()).errors, [])

    def test_never_politics_tribe_religion_vices_or_real_people(self):
        for text, why in (("Wewe ni kama Ruto na promises", "politics"), ("Hii ni tabia ya wakikuyu", "tribe"),
                          ("Pastor ameomba sadaka tena", "religion"), ("Twende tukunywe pombe", "alcohol"),
                          ("Safaricom wamekula bundles zangu", "real person or brand")):
            errs = self.line(text)
            self.assertTrue(any(why.split()[0] in e for e in errs), (text, errs))

    def test_insults_are_caught_by_the_guard(self):
        lines = scene()["lines"]
        lines[2] = {"who": "brayo", "text": "Mzee wewe ni fala", "do": "none"}
        self.assertTrue(any("not clean" in e for e in guard.check(scene(lines=lines)).errors))

    def test_shape(self):
        self.assertTrue(self.line("one two three four five six seven eight nine ten eleven twelve thirteen fourteen"))
        self.assertTrue(self.line("Haha \U0001F602"))
        self.assertTrue(self.line("Sawa", do="dance"))                     # no such action
        self.assertTrue(self.line("Sawa", face="crying"))                  # no such face
        self.assertTrue(self.errors(place="office"))
        self.assertTrue(self.errors(cast=["brayo"]))
        self.assertTrue(self.errors(cast=["brayo", "landlord", "sasha", "kevo"]))
        self.assertTrue(self.errors(cast=["brayo", "landlord", "sasha"]))  # Sasha never speaks
        self.assertTrue(self.errors(lines=scene()["lines"][:3]))
        self.assertTrue(self.errors(title="x" * 50))

    def test_walking_in_and_out_happens_once_in_the_right_place(self):
        lines = scene()["lines"]
        self.assertTrue(self.errors(lines=lines[:3] + [dict(lines[3], do="walk_in")] + lines[4:]))      # not his first line
        self.assertTrue(self.errors(lines=[dict(lines[0], do="walk_out")] + lines[1:]))                 # he speaks again later
        self.assertTrue(self.errors(place="matatu"))                                                     # a matatu is moving


class Editor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(mtaa, "SITUATIONS", Path(self.tmp.name) / "s.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def writer(self, first, again, scores):
        rounds = []

        def call(system, user, n):
            if system == mtaa.SCORE_RULES:
                return json.dumps({"scores": scores.pop(0)})
            rounds.append(user)
            return json.dumps({"posts": first if len(rounds) == 1 else again})
        return call, rounds

    def slot_and_body(self):
        s = scene()
        slot = {k: s[k] for k in ("id", "template", "publish_at", "size", "bg")}
        return slot, {"id": slot["id"], **{k: v for k, v in s.items() if k not in slot}}

    def test_a_good_scene_goes_through_marked_fiction(self):
        slot, body = self.slot_and_body()
        body["caption"] = "Rent day. Who is your Brayo? #MtaaMode #Nairobi"
        call, rounds = self.writer([body], [], [[{"id": slot["id"], "funny": 8, "true": 8, "voice": 8, "clean": 9, "note": "ok"}]])
        out = mtaa.write_scenes([slot], call=call)
        self.assertEqual(len(rounds), 1)
        self.assertIn("Animated skit: characters are fictional.", out[0]["caption"])
        self.assertTrue(out[0]["caption"].rstrip().endswith("#MtaaMode #Nairobi"))
        self.assertEqual(out[0]["critic"]["avg"], 8.25)
        self.assertEqual(mtaa.auto_problem(out[0]), "")

    def test_a_weak_scene_is_rewritten_once_and_the_better_one_kept(self):
        slot, weak = self.slot_and_body()
        better = dict(weak, title="Nia safi")
        call, rounds = self.writer([weak], [better], [
            [{"id": slot["id"], "funny": 5, "true": 6, "voice": 6, "clean": 9, "note": "sharper turn"}],
            [{"id": slot["id"], "funny": 8, "true": 8, "voice": 7, "clean": 9, "note": "ok"}]])
        out = mtaa.write_scenes([slot], call=call)
        self.assertEqual(len(rounds), 2)
        self.assertIn("sharper turn", rounds[1])
        self.assertEqual(out[0]["title"], "Nia safi")
        self.assertEqual(out[0]["critic"]["avg"], 8.0)

    def test_a_rewrite_that_breaks_a_rule_is_not_taken(self):
        slot, weak = self.slot_and_body()
        broken = dict(weak, place="office")
        call, _ = self.writer([weak], [broken], [
            [{"id": slot["id"], "funny": 6, "true": 6, "voice": 6, "clean": 9, "note": "x"}],
            [{"id": slot["id"], "funny": 9, "true": 9, "voice": 9, "clean": 9, "note": "x"}]])
        out = mtaa.write_scenes([slot], call=call)
        self.assertEqual(out[0]["place"], "plot")
        self.assertTrue(mtaa.auto_problem(out[0]))   # the weak original waits for a person

    def test_an_unwritten_slot_comes_back_empty_for_a_person(self):
        slot = {"id": "x", "template": "scene", "publish_at": "2026-11-09T12:45:00+03:00"}
        out = mtaa.write_scenes([slot], call=lambda system, user, n: "not json")
        self.assertFalse(out[0].get("lines"))
        self.assertTrue(mtaa.auto_problem(out[0]))

    def test_samples_never_use_up_a_situation(self):
        slot, body = self.slot_and_body()
        call, _ = self.writer([dict(body, situation="rent day")], [],
                              [[{"id": slot["id"], "funny": 8, "true": 8, "voice": 8, "clean": 9, "note": "ok"}]])
        mtaa.draft([slot], call=call, remember=False)
        self.assertFalse(mtaa.SITUATIONS.exists())

    def test_auto_approval_needs_the_bar_and_a_clean_score(self):
        self.assertIn("missing", mtaa.auto_problem(scene()))
        self.assertIn("scored", mtaa.auto_problem(scene(critic={"avg": 6.5, "clean": 9})))
        self.assertIn("clean", mtaa.auto_problem(scene(critic={"avg": 8, "clean": 7})))
        self.assertEqual(mtaa.auto_problem(scene(critic={"avg": 7.5, "clean": 9})), "")


class Rendered(unittest.TestCase):
    """Both templates drawn by the real browser under the Mtaa Mode brand: the still frame (the feed picture and the
    Reel's cover) passes the layout check, both of the cast are on stage, and the hook line's bubble is on screen."""

    def test_still_frames(self):
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            self.skipTest("playwright not installed")
        songs, as_of = mtaa.chart_songs(key="k", now=NOW, get=lambda url: json.dumps(items(REAL)))
        chart = mtaa.chart_post({"id": "t-chart", "template": "chart", "publish_at": "2026-11-09T17:30:00+03:00",
                                 "size": "story", "bg": "usiku"}, songs, as_of)
        posts_in = [scene(), scene(id="t-matatu", place="matatu", cast=["sasha", "kevo", "dee"],
                                   lines=[{"who": w, "text": "Line for the layout check only.", "do": "none"}
                                          for w in ("sasha", "kevo", "dee", "sasha")]), chart]
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts.json"
            posts.write_text(json.dumps(posts_in, ensure_ascii=False), encoding="utf-8")
            script = textwrap.dedent(f"""
                import json, sys
                sys.path.insert(0, {str(HERE)!r})
                import render
                from playwright.sync_api import sync_playwright
                env = render.make_env()
                out = []
                with sync_playwright() as p:
                    b = p.chromium.launch(); pg = b.new_page(viewport={{"width": 1080, "height": 1920}})
                    for post in json.load(open({str(posts)!r})):
                        f = {tmp!r} + "/" + post["id"] + ".html"
                        open(f, "w").write(render.build_html(env, post))
                        pg.goto("file://" + f); pg.evaluate("document.fonts.ready.then(() => window.__fit())")
                        qa = pg.evaluate(render.QA_JS)
                        seen = pg.evaluate("(() => {{ const c = document.getElementById('cast'); if (!c) return null;"
                                           " const shown = [...c.children].filter(g => g.getAttribute('visibility') !== 'hidden')"
                                           ".map(g => g.getBoundingClientRect()).filter(r => r.left > -50 && r.right < 1130);"
                                           " const b = [...document.querySelectorAll('.bub')].filter(x => x.style.display === 'block')"
                                           ".map(x => x.getBoundingClientRect());"
                                           " return {{cast: shown.length, bubbles: b.map(r => [r.left, r.top, r.right, r.bottom])}}; }})()")
                        out.append({{"id": post["id"], "qa": qa, "seen": seen}})
                    b.close()
                print(json.dumps(out))
            """)
            run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=180,
                                 env={**os.environ, "KOR_BRAND": "mtaamode"})
            if run.returncode and "Executable doesn't exist" in run.stderr:
                self.skipTest("no browser installed")
            self.assertEqual(run.returncode, 0, run.stderr[-800:])
            got = {r["id"]: r for r in json.loads(run.stdout.strip().splitlines()[-1])}
        for pid in ("t-chart", scene()["id"], "t-matatu"):
            self.assertEqual(got[pid]["qa"], [], pid)
        for pid, n in ((scene()["id"], 2), ("t-matatu", 3)):
            seen = got[pid]["seen"]
            self.assertEqual(seen["cast"], n, pid)
            self.assertEqual(len(seen["bubbles"]), 1, pid)
            left, top, right, bottom = seen["bubbles"][0]
            self.assertGreaterEqual(left, 40)
            self.assertLessEqual(right, 1040)
            self.assertGreaterEqual(top, 340)


if __name__ == "__main__":
    unittest.main()
