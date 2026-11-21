from unittest import mock

import datetime

import shutil

import tempfile

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from productdle import logic, stats, views
from productdle.repository import DatabaseUnavailable

from .factories import FakeRepository, make_product


@override_settings(SECURE_SSL_REDIRECT=False)
class ViewTest(SimpleTestCase):
    def setUp(self):
        logic._target_cache.clear()
        # Never write the tally into the checkout during tests.
        self.stats_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.stats_dir, ignore_errors=True)
        override = override_settings(STREGDLE_STATS_DIR=self.stats_dir)
        override.enable()
        self.addCleanup(override.disable)
        self.cola = make_product(
            id=1, name="Cola", price=2500, caffeine_mg=34, categories=["Sodavand"], rooms=["Kælder"]
        )
        self.beer = make_product(id=2, name="Mørk øl", price=3000, alcohol_ml=7.5, categories=["Øl"])
        self.repo = FakeRepository([self.cola, self.beer])
        patcher = mock.patch.object(views, "repository", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        logic._target_cache.clear()

    def test_index_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stregsystemdle")
        # The share button and the date it puts in the message.
        self.assertContains(response, 'id="shareBtn"')
        self.assertContains(response, 'var TODAY = "')
        self.assertContains(response, """SQUARES = { correct: '\\uD83D\\uDFE9'""")
        # Guesses survive a reload via localStorage, keyed by the day.
        self.assertContains(response, "var STORE_KEY = 'stregdle:' + TODAY;")
        self.assertContains(response, "restore();")
        # Guesses carry the anonymous player id the statistics page counts.
        self.assertContains(response, "encodeURIComponent(PLAYER)")
        self.assertContains(response, "var PLAYER_KEY = 'stregdle:player';")

    def test_healthz_is_cheap_and_ok(self):
        # No database access: the pool is not even consulted on this path.
        with mock.patch.object(self.repo, "products", side_effect=AssertionError("db touched")):
            response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_search_returns_matching_products(self):
        data = self.client.get("/search/", {"q": "cola"}).json()
        self.assertEqual([p["id"] for p in data["products"]], ["1"])
        self.assertEqual(data["products"][0]["name"], "Cola")

    def test_search_without_query_is_empty(self):
        self.assertEqual(self.client.get("/search/").json(), {"products": []})

    def test_guess_reports_direction(self):
        target = logic.daily_target(self.repo.products())
        wrong = self.beer if target.id == self.cola.id else self.cola
        data = self.client.get("/guess/", {"id": wrong.id}).json()
        self.assertFalse(data["won"])
        self.assertEqual({c["key"] for c in data["columns"]}, {c["key"] for c in logic.COLUMNS})

    def test_guess_can_win(self):
        target = logic.daily_target(self.repo.products())
        data = self.client.get("/guess/", {"id": target.id}).json()
        self.assertTrue(data["won"])
        self.assertTrue(all(c["status"] == "correct" for c in data["columns"]))

    def test_guess_unknown_id_is_404(self):
        self.assertEqual(self.client.get("/guess/", {"id": "999"}).status_code, 404)
        self.assertEqual(self.client.get("/guess/", {"id": "abc"}).status_code, 404)

    def test_reveal_shows_target(self):
        target = logic.daily_target(self.repo.products())
        data = self.client.get("/reveal/").json()
        self.assertEqual(data["name"], logic.clean_name(target.name))
        self.assertTrue(all(c["status"] == "correct" for c in data["columns"]))

    def test_reveal_carries_the_photo(self):
        # A single-product pool, so the answer is known.
        repo = FakeRepository([make_product(id=9, name="Tuborg Grøn")])
        with mock.patch.object(views, "repository", repo):
            data = self.client.get("/reveal/").json()
        self.assertEqual(data["image"], "/static/productdle/wares/tuborg-groen.png")

    def test_database_failure_is_503(self):
        with mock.patch.object(self.repo, "products", side_effect=DatabaseUnavailable("boom")):
            with self.assertLogs("productdle.views", level="WARNING"):
                for url in ("/search/?q=cola", "/guess/?id=1", "/reveal/"):
                    self.assertEqual(self.client.get(url).status_code, 503, url)

    def test_guess_is_tallied(self):
        target = logic.daily_target(self.repo.products())
        self.client.get("/guess/", {"id": target.id, "p": "aaaaaaaa11"})
        summary = stats.summary()
        self.assertEqual(summary["guesses"], 1)
        self.assertEqual(summary["players"], 1)
        self.assertEqual(summary["solvers"], 1)

    def test_give_up_is_tallied(self):
        self.client.get("/reveal/", {"p": "aaaaaaaa11"})
        self.assertEqual(stats.summary()["gave_up"], 1)

    def test_statistics_page_counts_the_day(self):
        target = logic.daily_target(self.repo.products())
        wrong = self.beer if target.id == self.cola.id else self.cola
        self.client.get("/guess/", {"id": wrong.id, "p": "aaaaaaaa11"})
        self.client.get("/guess/", {"id": target.id, "p": "aaaaaaaa11"})
        self.client.get("/guess/", {"id": wrong.id, "p": "bbbbbbbb22"})

        response = self.client.get("/statistics/")
        self.assertEqual(response.status_code, 200)
        page = response.context["stats"]
        self.assertEqual((page["players"], page["guesses"], page["solvers"], page["gave_up"]), (2, 3, 1, 0))
        self.assertContains(response, "deltagere")
        self.assertContains(response, "I dag, ")
        self.assertContains(response, 'http-equiv="refresh"')
        self.assertContains(response, "opdateres automatisk")

    def test_statistics_page_names_the_day_in_danish(self):
        page = self.client.get("/statistics/").content.decode()
        weekdays = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
        self.assertTrue(any(day in page for day in weekdays), page[page.find("I dag,") :][:40])

    def test_statistics_page_shows_no_answer_and_no_guessed_names(self):
        target = logic.daily_target(self.repo.products())
        response = self.client.get("/statistics/")
        self.assertNotContains(response, logic.clean_name(target.name))
        self.assertNotContains(response, logic.clean_name(self.beer.name))
        self.assertNotContains(response, logic.clean_name(self.cola.name))

    def test_statistics_page_survives_a_database_outage(self):
        with mock.patch.object(self.repo, "products", side_effect=DatabaseUnavailable("boom")):
            response = self.client.get("/statistics/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["stats"]["guesses"], 0)

    def test_statistics_page_counts_only_today(self):
        target = logic.daily_target(self.repo.products())
        self.client.get("/guess/", {"id": target.id, "p": "aaaaaaaa11"})

        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        with mock.patch.object(views.timezone, "localdate", return_value=tomorrow):
            response = self.client.get("/statistics/")

        page = response.context["stats"]
        self.assertEqual((page["guesses"], page["players"], page["solvers"]), (0, 0, 0))
        self.assertEqual(response.context["yesterday"]["guesses"], 1)
        self.assertEqual(response.context["day"], tomorrow)
        self.assertContains(response, "Ingen gæt endnu")
        self.assertContains(response, "I går klarede 1 af 1 den.")
