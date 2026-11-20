import datetime

import random

from django.test import SimpleTestCase

from productdle import logic

from .factories import make_product


class DailyTargetTest(SimpleTestCase):
    def setUp(self):
        logic._target_cache.clear()
        self.products = [
            make_product(id=1, name="Cola", price=2500, caffeine_mg=34, categories=["Sodavand"], rooms=["Kælder"]),
            make_product(id=2, name="Mørk øl", price=3000, alcohol_ml=7.5, categories=["Øl"]),
        ]

    def tearDown(self):
        logic._target_cache.clear()

    def test_pick_is_deterministic_per_day(self):
        day = datetime.date(2026, 11, 11)
        rng1 = random.Random(f"{logic.SEED_PREFIX}-{day.isoformat()}")
        rng2 = random.Random(f"{logic.SEED_PREFIX}-{day.isoformat()}")
        self.assertEqual(rng1.choice(self.products).id, rng2.choice(self.products).id)

    def test_daily_target_is_same_for_the_day(self):
        first = logic.daily_target(self.products)
        second = logic.daily_target(self.products)
        self.assertIsNotNone(first)
        self.assertEqual(first.id, second.id)

    def test_empty_pool_has_no_target(self):
        self.assertIsNone(logic.daily_target([]))

    def test_target_survives_a_reordered_pool(self):
        first = logic.daily_target(self.products)
        reordered = list(reversed(self.products))
        self.assertEqual(logic.daily_target(reordered).id, first.id)


class CompareTest(SimpleTestCase):
    def setUp(self):
        self.cola = make_product(
            id=1,
            name="Cola",
            price=2500,
            caffeine_mg=34,
            categories=["Sodavand"],
            rooms=["Kælder"],
            sales_window=3,
            total_sales=2,
        )
        self.beer = make_product(
            id=2, name="Mørk øl", price=3000, alcohol_ml=7.5, categories=["Øl"], sales_window=30, total_sales=10
        )

    def test_compare_exact_product_all_correct(self):
        columns = logic.compare(self.cola, self.cola)
        self.assertTrue(all(c["status"] == "correct" for c in columns))

    def test_compare_columns_for_guess_vs_target(self):
        # Cola vs beer: cheaper, different category, no alcohol but caffeine,
        # different room, and far fewer sales.
        by_key = {c["key"]: c for c in logic.compare(self.cola, self.beer)}
        self.assertEqual(by_key["id"]["status"], "low")
        self.assertEqual(by_key["price"]["status"], "low")
        self.assertEqual(by_key["category"]["status"], "wrong")
        self.assertEqual(by_key["alcohol"]["status"], "low")  # 0 ml < 7.5 ml
        self.assertEqual(by_key["caffeine"]["status"], "high")  # 34 mg > 0 mg
        self.assertEqual(by_key["rooms"]["status"], "wrong")
        self.assertEqual(by_key["sales"]["status"], "low")
        self.assertEqual(by_key["total"]["status"], "low")

    def test_compare_values_are_used_in_cells(self):
        by_key = {c["key"]: c for c in logic.compare(self.cola, self.beer)}
        self.assertEqual(by_key["price"]["value"], "25.00")
        self.assertEqual(by_key["alcohol"]["value"], "0.0 ml")
        self.assertEqual(by_key["caffeine"]["value"], "34 mg")
        self.assertEqual(by_key["rooms"]["value"], "Kælder")

    def test_shared_category_counts_as_correct(self):
        other_soda = make_product(id=3, name="Fanta", price=2500, categories=["Sodavand"])
        by_key = {c["key"]: c for c in logic.compare(self.cola, other_soda)}
        self.assertEqual(by_key["category"]["status"], "correct")

    def test_sales_within_two_are_correct(self):
        # 3 sales in the window is 1/month, 6 sales is 2/month: within tolerance.
        close = make_product(id=4, name="Vand", sales_window=6)
        by_key = {c["key"]: c for c in logic.compare(self.cola, close)}
        self.assertEqual(by_key["sales"]["status"], "correct")

    def test_empty_category_and_rooms_render_as_dash(self):
        bare = make_product(id=5, name="Gaffel", categories=(), rooms=())
        stats = logic.product_stats(bare)
        self.assertEqual(stats["category"], "-")
        self.assertEqual(stats["rooms"], "-")


class ProductStatsTest(SimpleTestCase):
    def test_product_stats_shape(self):
        product = make_product(
            id=1,
            name="Cola",
            price=2500,
            caffeine_mg=34,
            categories=["Sodavand"],
            rooms=["Kælder"],
            alias="cola",
            sales_window=3,
            total_sales=2,
        )
        self.assertEqual(
            logic.product_stats(product),
            {
                "id": "1",
                "name": "Cola",
                "alias": "cola",
                "price": "25.00",
                "category": "Sodavand",
                "alcohol": "0.0 ml",
                "caffeine": "34 mg",
                "rooms": "Kælder",
                "sales": "1",
                "total": "2",
            },
        )

    def test_clean_name_strips_markup(self):
        self.assertEqual(logic.clean_name("Cocio <b>(Mellem)</b>"), "Cocio (Mellem)")


class SearchTest(SimpleTestCase):
    def setUp(self):
        self.products = [
            make_product(id=7, name="ChokoMælk", price=1500, alias="choko"),
            make_product(id=8, name="Cola", price=2500),
        ]

    def test_search_matches_danish_case_insensitive(self):
        ids = [p.id for p in logic.search_products(self.products, "CHOKOMÆLK", 10)]
        self.assertIn(7, ids)

    def test_search_matches_alias_case_insensitive(self):
        ids = [p.id for p in logic.search_products(self.products, "CHOKO", 10)]
        self.assertIn(7, ids)

    def test_search_matches_id(self):
        ids = [p.id for p in logic.search_products(self.products, "8", 10)]
        self.assertEqual(ids, [8])

    def test_empty_query_matches_nothing(self):
        self.assertEqual(logic.search_products(self.products, "  ", 10), [])

    def test_limit_is_respected(self):
        self.assertEqual(len(logic.search_products(self.products, "o", 1)), 1)
