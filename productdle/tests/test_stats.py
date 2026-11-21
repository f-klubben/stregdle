import datetime

import json

import shutil

import tempfile

from django.test import SimpleTestCase, override_settings

from productdle import stats

DAY = datetime.date(2026, 11, 20)


class StatsTest(SimpleTestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        override = override_settings(STREGDLE_STATS_DIR=self.dir)
        override.enable()
        self.addCleanup(override.disable)

    def events(self, day=DAY):
        with open(stats._path(day), encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    def test_attempts_count_up_per_player(self):
        self.assertEqual(stats.record_guess("aaaaaaaa11", 3, False, day=DAY), 1)
        self.assertEqual(stats.record_guess("aaaaaaaa11", 4, False, day=DAY), 2)
        # Another player starts over at 1.
        self.assertEqual(stats.record_guess("bbbbbbbb22", 4, True, day=DAY), 1)

        summary = stats.summary(DAY)
        self.assertEqual(summary["players"], 2)
        self.assertEqual(summary["guesses"], 3)
        self.assertEqual(summary["solvers"], 1)

    def test_attempt_number_is_stored(self):
        stats.record_guess("aaaaaaaa11", 3, False, day=DAY)
        stats.record_guess("aaaaaaaa11", 3, True, day=DAY)
        self.assertEqual([event["a"] for event in self.events()], [1, 2])
        self.assertEqual([event["won"] for event in self.events()], [False, True])

    def test_win_distribution_and_average(self):
        stats.record_guess("aaaaaaaa11", 1, True, day=DAY)
        stats.record_guess("bbbbbbbb22", 1, False, day=DAY)
        stats.record_guess("bbbbbbbb22", 2, True, day=DAY)

        summary = stats.summary(DAY)
        self.assertEqual(summary["average"], 1.5)
        self.assertEqual(summary["solved_pct"], 100)
        self.assertEqual([row["players"] for row in summary["distribution"]], [1, 1, 0, 0, 0, 0, 0])

    def test_long_runs_land_in_the_last_bucket(self):
        for attempt in range(1, 9):
            stats.record_guess("aaaaaaaa11", attempt, attempt == 8, day=DAY)
        summary = stats.summary(DAY)
        self.assertEqual(summary["distribution"][-1]["label"], "7+")
        self.assertEqual(summary["distribution"][-1]["players"], 1)

    def test_gave_up_is_counted_once_per_player(self):
        stats.record_guess("aaaaaaaa11", 1, False, day=DAY)
        stats.record_gave_up("aaaaaaaa11", day=DAY)
        self.assertEqual(stats.summary(DAY)["gave_up"], 1)

    def test_a_solver_does_not_also_count_as_giving_up(self):
        stats.record_guess("aaaaaaaa11", 1, True, day=DAY)
        stats.record_gave_up("aaaaaaaa11", day=DAY)
        summary = stats.summary(DAY)
        self.assertEqual(summary["solvers"], 1)
        self.assertEqual(summary["gave_up"], 0)

    def test_anonymous_guesses_count_but_are_not_players(self):
        stats.record_guess(None, 1, True, day=DAY)
        summary = stats.summary(DAY)
        self.assertEqual(summary["guesses"], 1)
        self.assertEqual(summary["players"], 0)
        self.assertEqual(summary["solvers"], 1)
        self.assertEqual(summary["solved_pct"], 0)
        self.assertEqual(self.events()[0]["p"], "")

    def test_a_dead_player_id_is_ignored(self):
        self.assertIsNone(stats.valid_player("../../etc/passwd"))
        self.assertIsNone(stats.valid_player(""))
        self.assertEqual(stats.valid_player("  AAAAAAAA11 "), "aaaaaaaa11")
        stats.record_guess("../../etc/passwd", 1, False, day=DAY)
        self.assertEqual(self.events()[0]["p"], "")

    def test_broken_lines_are_skipped(self):
        with open(stats._path(DAY), "w", encoding="utf-8") as handle:
            handle.write("not json\n")
            handle.write(json.dumps({"k": "guess", "t": "2026-11-20T10:00:00+01:00", "p": "aaaaaaaa11", "a": 1}) + "\n")
            handle.write(json.dumps({"k": "other"}) + "\n")
        self.assertEqual(stats.summary(DAY)["guesses"], 1)

    def test_hours_follow_the_timestamps(self):
        with open(stats._path(DAY), "w", encoding="utf-8") as handle:
            for hour in (9, 9, 14):
                handle.write(
                    json.dumps(
                        {
                            "k": "guess",
                            "t": f"2026-11-20T{hour:02d}:05:00+01:00",
                            "p": "aaaaaaaa11",
                            "a": 1,
                        }
                    )
                    + "\n"
                )
        summary = stats.summary(DAY)
        self.assertEqual(summary["hours"][9]["guesses"], 2)
        self.assertEqual(summary["hours"][9]["pct"], 100)
        self.assertEqual(summary["hours"][14]["pct"], 50)

    def test_days_are_separate_files(self):
        stats.record_guess("aaaaaaaa11", 1, True, day=DAY)
        self.assertEqual(stats.summary(DAY - datetime.timedelta(days=1))["guesses"], 0)
        self.assertEqual(stats.yesterday(DAY + datetime.timedelta(days=1))["solvers"], 1)

    def test_tally_can_be_switched_off(self):
        with override_settings(STREGDLE_STATS_DIR=""):
            self.assertEqual(stats.record_guess("aaaaaaaa11", 1, True, day=DAY), 1)
            stats.record_gave_up("aaaaaaaa11", day=DAY)
            summary = stats.summary(DAY)
        self.assertEqual(summary["guesses"], 0)
        self.assertEqual(summary["players"], 0)

    def test_empty_day_is_all_zeroes(self):
        summary = stats.summary(DAY)
        self.assertEqual(summary["guesses"], 0)
        self.assertEqual(summary["players"], 0)
        self.assertIsNone(summary["average"])
        self.assertEqual(len(summary["hours"]), 24)
        self.assertTrue(all(hour["pct"] == 0 for hour in summary["hours"]))
        self.assertTrue(all(row["pct"] == 0 for row in summary["distribution"]))

    def test_a_thin_bar_still_registers(self):
        # One solver among a big day must not round down to an invisible bar.
        for i in range(60):
            stats.record_guess(f"p{i:03d}abcdef", 5, False, day=DAY)
        stats.record_guess("aaaaaaaa11", 5, True, day=DAY)
        summary = stats.summary(DAY)
        self.assertEqual(summary["distribution"][0]["players"], 1)
        self.assertGreaterEqual(summary["distribution"][0]["pct"], 2)
