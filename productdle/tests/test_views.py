from unittest import mock

from django.test import SimpleTestCase

from productdle import logic, views
from productdle.repository import DatabaseUnavailable

from .factories import FakeRepository, make_product


class ViewTest(SimpleTestCase):
    def setUp(self):
        logic._target_cache.clear()
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
            with self.assertLogs("productdle.views", level="ERROR"):
                for url in ("/search/?q=cola", "/guess/?id=1", "/reveal/"):
                    self.assertEqual(self.client.get(url).status_code, 503, url)
