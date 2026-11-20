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
        # Cola vs beer: cheaper, different category, no alcohol, different
        # room, and far fewer sales.
        by_key = {c["key"]: c for c in logic.compare(self.cola, self.beer)}
        self.assertEqual(by_key["id"]["status"], "low")
        self.assertEqual(by_key["price"]["status"], "low")
        self.assertEqual(by_key["category"]["status"], "wrong")
        self.assertEqual(by_key["alcohol"]["status"], "low")  # 0 ml < 7.5 ml
        self.assertEqual(by_key["rooms"]["status"], "wrong")
        self.assertEqual(by_key["sales"]["status"], "low")
        self.assertEqual(by_key["total"]["status"], "low")

    def test_compare_values_are_used_in_cells(self):
        by_key = {c["key"]: c for c in logic.compare(self.cola, self.beer)}
        self.assertEqual(by_key["price"]["value"], "25.00")
        self.assertEqual(by_key["alcohol"]["value"], "0.0 ml")
        self.assertEqual(by_key["rooms"]["value"], "Kælder")

    def test_shared_category_is_partial_not_correct(self):
        # Same single category is a full match; sharing one of several is not.
        same = make_product(id=3, name="Fanta", categories=["Sodavand"])
        by_key = {c["key"]: c for c in logic.compare(self.cola, same)}
        self.assertEqual(by_key["category"]["status"], "correct")

        wider = make_product(id=4, name="Cola & Fanta", categories=["Sodavand", "Øl"])
        by_key = {c["key"]: c for c in logic.compare(self.cola, wider)}
        self.assertEqual(by_key["category"]["status"], "partial")

    def test_rooms_follow_the_same_rule(self):
        two_rooms = make_product(id=5, name="Begge", rooms=["Kælder", "Stuen"])
        by_key = {c["key"]: c for c in logic.compare(self.cola, two_rooms)}
        self.assertEqual(by_key["rooms"]["status"], "partial")

        same_room = make_product(id=6, name="Kælder", rooms=["Kælder"])
        by_key = {c["key"]: c for c in logic.compare(self.cola, same_room)}
        self.assertEqual(by_key["rooms"]["status"], "correct")

        other_room = make_product(id=7, name="Stuen", rooms=["Stuen"])
        by_key = {c["key"]: c for c in logic.compare(self.cola, other_room)}
        self.assertEqual(by_key["rooms"]["status"], "wrong")

    def test_empty_sets_match_each_other(self):
        bare = make_product(id=8, name="Gaffel", categories=(), rooms=())
        by_key = {c["key"]: c for c in logic.compare(bare, bare)}
        self.assertEqual(by_key["category"]["status"], "correct")
        self.assertEqual(by_key["rooms"]["status"], "correct")

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


class LayoutTest(SimpleTestCase):
    def test_columns(self):
        keys = [c["key"] for c in logic.COLUMNS]
        self.assertNotIn("caffeine", keys)
        self.assertIn("last_sale", keys)
        self.assertIn("named", keys)
        self.assertEqual(keys[:2], ["id", "price"])


class NamedAndLastSaleTest(SimpleTestCase):
    def test_named_column_is_a_boolean_match(self):
        yes = make_product(id=1, name="Cola", alias="cola")
        also_yes = make_product(id=2, name="Fanta", alias="fanta")
        no = make_product(id=3, name="Vand")
        by_key = {c["key"]: c for c in logic.compare(yes, also_yes)}
        self.assertEqual(by_key["named"]["status"], "correct")
        self.assertEqual(by_key["named"]["value"], "Ja")

        by_key = {c["key"]: c for c in logic.compare(yes, no)}
        self.assertEqual(by_key["named"]["status"], "wrong")
        self.assertEqual(by_key["named"]["value"], "Ja")
        self.assertEqual(logic.named_str(no), "Nej")

    def test_last_sale_is_directional(self):
        recent = make_product(id=1, name="Cola", last_sale_days=3)
        old = make_product(id=2, name="Fanta", last_sale_days=40)

        by_key = {c["key"]: c for c in logic.compare(recent, old)}
        self.assertEqual(by_key["last_sale"]["status"], "low")
        self.assertEqual(by_key["last_sale"]["value"], "3 dage")

        by_key = {c["key"]: c for c in logic.compare(old, recent)}
        self.assertEqual(by_key["last_sale"]["status"], "high")

    def test_never_sold_products(self):
        never = make_product(id=1, name="Ny vare")
        sold = make_product(id=2, name="Cola", last_sale_days=5)

        by_key = {c["key"]: c for c in logic.compare(never, never)}
        self.assertEqual(by_key["last_sale"]["status"], "correct")
        self.assertEqual(by_key["last_sale"]["value"], "aldrig")

        by_key = {c["key"]: c for c in logic.compare(never, sold)}
        self.assertEqual(by_key["last_sale"]["status"], "wrong")

    def test_last_sale_wording(self):
        self.assertEqual(logic.last_sale_str(None), "aldrig")
        self.assertEqual(logic.last_sale_str(0), "i dag")
        self.assertEqual(logic.last_sale_str(1), "1 dag")
        self.assertEqual(logic.last_sale_str(12), "12 dage")


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
            last_sale_days=4,
        )
        self.assertEqual(
            logic.product_stats(product),
            {
                "id": "1",
                "name": "Cola",
                "alias": "cola",
                "image": "",
                "price": "25.00",
                "category": "Sodavand",
                "alcohol": "0.0 ml",
                "rooms": "Kælder",
                "sales": "1",
                "total": "2",
                "last_sale": "4 dage",
                "named": "Ja",
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
