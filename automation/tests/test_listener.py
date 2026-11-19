import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import listener  # noqa: E402

CHAT = "42"


def tap(uid, data="a|2026-W42|p1", chat=CHAT):
    return {"update_id": uid, "callback_query": {"id": f"q{uid}", "data": data, "message": {"chat": {"id": int(chat)}}}}


class ListenerTests(unittest.TestCase):
    def test_only_owner_taps_and_clips_count(self):
        self.assertEqual(listener.classify(tap(1), CHAT), "tap")
        self.assertIsNone(listener.classify(tap(2, chat="7"), CHAT))
        self.assertEqual(listener.classify({"update_id": 3, "message": {"chat": {"id": 42}, "video": {}}}, CHAT), "clip")
        # a text from the owner is now a note for Claude: it wakes the run that saves it
        self.assertEqual(listener.classify({"update_id": 4, "message": {"chat": {"id": 42}, "text": "hi"}}, CHAT), "clip")

    def test_ack_says_what_happened(self):
        self.assertIn("Approved", listener.ack_text(tap(1, "a|w|p")))
        self.assertIn("Rejected", listener.ack_text(tap(1, "r|w|p")))
        self.assertIn("Working", listener.ack_text(tap(1, "c|r|123")))

    def test_new_tap_is_answered_and_starts_one_run(self):
        polls = [{"result": []}, {"result": [tap(5), tap(6, "r|2026-W42|p2")]}] + [{"result": [tap(5), tap(6, "r|2026-W42|p2")]}] * 50
        calls, runs = [], []

        def fake_tg(method, fields):
            calls.append(method)
            return polls.pop(0) if method == "getUpdates" else {"ok": True}
        clock = iter(range(0, 10_000, 5))
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": CHAT}), mock.patch.object(listener, "tg", fake_tg), \
                mock.patch.object(listener, "dispatch", lambda c: runs.append(c) or True), \
                mock.patch.object(listener.time, "sleep", lambda s: None), mock.patch.object(listener, "schedule", lambda: []), \
                mock.patch.object(listener.time, "time", lambda: next(clock)):
            listener.run(minutes=3)
        self.assertEqual(calls.count("answerCallbackQuery"), 2)
        self.assertEqual(runs, ["tick"])

    def test_leftover_taps_at_startup_are_not_answered_but_still_run(self):
        polls = [{"result": [tap(1)]}] * 50
        calls, runs = [], []

        def fake_tg(method, fields):
            calls.append(method)
            return polls.pop(0) if method == "getUpdates" else {"ok": True}
        clock = iter(range(0, 10_000, 5))
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": CHAT}), mock.patch.object(listener, "tg", fake_tg), \
                mock.patch.object(listener, "dispatch", lambda c: runs.append(c) or True), \
                mock.patch.object(listener.time, "sleep", lambda s: None), mock.patch.object(listener, "schedule", lambda: []), \
                mock.patch.object(listener.time, "time", lambda: next(clock)):
            listener.run(minutes=2)
        self.assertNotIn("answerCallbackQuery", calls)
        self.assertEqual(runs, ["tick"])


    def test_due_post_starts_one_run_on_time(self):
        calls, runs = [], []
        clock = iter(range(0, 10_000, 5))
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": CHAT}), \
                mock.patch.object(listener, "tg", lambda m, f: {"result": []}), \
                mock.patch.object(listener, "dispatch", lambda c: runs.append(c) or True), \
                mock.patch.object(listener.time, "sleep", lambda s: None), \
                mock.patch.object(listener, "schedule", lambda: [("p1#0", 60.0), ("p2#0", 99_999.0)]), \
                mock.patch.object(listener.time, "time", lambda: next(clock)):
            listener.run(minutes=5)
        self.assertEqual(runs, ["tick"])   # p1 once, p2 not yet due

    def test_schedule_reads_approved_posts_with_eat_times(self):
        week = {"posts": [{"id": "a", "status": "approved", "publish_at": "2026-10-13T12:45:00+03:00"},
                          {"id": "b", "status": "awaiting", "publish_at": "2026-10-13T13:00:00+03:00"},
                          {"id": "c", "status": "publish_failed", "attempts": 1, "publish_at": "2026-10-13T12:45:00"}]}
        def fake(path, raw=False):
            return [{"name": "2026-W42.json"}] if path.endswith("weeks") else week
        with mock.patch.object(listener, "_gh", fake):
            got = dict(listener.schedule())
        self.assertEqual(set(got), {"a#0", "c#1"})
        self.assertEqual(got["a#0"], got["c#1"])   # a naive time is read as EAT


    def test_clock_fires_hot_daily_and_week_on_sunday_once(self):
        fired = set()
        utc = listener.dt.timezone.utc
        sun = listener.dt.datetime(2026, 10, 18, 14, 3, tzinfo=utc)
        self.assertEqual(listener.clock_due(sun, fired), ["week"])
        self.assertEqual(listener.clock_due(sun, fired), [])
        mon = listener.dt.datetime(2026, 10, 19, 6, 10, tzinfo=utc)
        self.assertEqual(listener.clock_due(mon, fired), ["hot"])
        self.assertEqual(listener.clock_due(mon.replace(hour=7, minute=10), set()), [])   # window over

    def test_clock_keeps_every_edition_and_the_two_hourly_tick(self):
        utc = listener.dt.timezone.utc
        thu = listener.dt.datetime(2026, 11, 19, 0, 0, tzinfo=utc)
        fired, got = set(), []
        for minute in range(0, 24 * 60, 1):   # a whole day, minute by minute
            got += [(c, f"{(thu + listener.dt.timedelta(minutes=minute)):%H:%M}")
                    for c in listener.clock_due(thu + listener.dt.timedelta(minutes=minute), fired)]
        self.assertIn(("hot --morning", "03:35"), got)     # 06:35 EAT: on 19 Nov the schedule started it at 15:04
        self.assertIn(("hot", "06:05"), got)
        self.assertIn(("hot --afternoon", "09:30"), got)
        self.assertIn(("hot --evening", "13:05"), got)
        self.assertEqual(sum(1 for c, _ in got if c == "hot --breaking"), 7)
        self.assertEqual(sum(1 for c, _ in got if c == "tick"), 12)
        self.assertNotIn("week", [c for c, _ in got])        # Thursday
        sat = listener.dt.datetime(2026, 11, 21, 6, 0, tzinfo=utc)
        self.assertIn("weekly", listener.clock_due(sat, set()))
        wed = listener.dt.datetime(2026, 11, 18, 14, 10, tzinfo=utc)
        self.assertIn("this-week", listener.clock_due(wed, set()))

    def _run(self, minutes, schedule, waiting, clock_step=5, clock_from=0):
        runs = []
        clock = iter(range(clock_from, clock_from + 100_000, clock_step))
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": CHAT}), \
                mock.patch.object(listener, "tg", lambda m, f: {"result": []}), \
                mock.patch.object(listener, "dispatch", lambda c: runs.append(c) or True), \
                mock.patch.object(listener.time, "sleep", lambda s: None), \
                mock.patch.object(listener, "schedule", schedule), \
                mock.patch.object(listener, "waiting_runs", waiting), \
                mock.patch.object(listener.time, "time", lambda: next(clock)):
            listener.run(minutes=minutes)
        return runs

    def test_nothing_starts_while_another_run_waits(self):
        # GitHub keeps one waiting run per group: a second start would cancel the first, so ours waits its turn
        self.assertEqual(self._run(5, lambda: [("p1#0", 0.0)], lambda: 1), [])

    def test_queued_commands_go_one_turn_at_a_time(self):
        clock_from = int(listener.dt.datetime(2026, 11, 19, 3, 34, tzinfo=listener.dt.timezone.utc).timestamp())
        answers = iter([0, 1, 1, 0] + [0] * 1000)
        runs = self._run(6, lambda: [("p1#0", 0.0)], lambda: next(answers), clock_from=clock_from)
        self.assertEqual(runs, ["tick", "hot --morning"])   # both started, never together

    def test_a_due_post_whose_run_vanished_gets_another(self):
        quiet = int(listener.dt.datetime(2026, 11, 19, 0, 30, tzinfo=listener.dt.timezone.utc).timestamp())
        runs = self._run(40, lambda: [("p1#0", 0.0)], lambda: 0, clock_step=1, clock_from=quiet)   # no clock run due
        self.assertEqual(runs, ["tick", "tick", "tick"])   # 0, 15 and 30 minutes: the post never went out


if __name__ == "__main__":
    unittest.main()
