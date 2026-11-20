from django.test import SimpleTestCase

from productdle import logic, wares


class WareImageTest(SimpleTestCase):
    def test_exact_name_matches(self):
        self.assertEqual(wares.image_for("Tuborg Grøn"), "/static/productdle/wares/tuborg-groen.png")

    def test_markup_and_punctuation_are_ignored(self):
        self.assertEqual(wares.image_for("Cocio <b>(Mellem)</b>"), "/static/productdle/wares/cocio.png")
        self.assertEqual(wares.image_for("FAXE-KONDI"), "/static/productdle/wares/faxe-kondi.png")

    def test_variant_suffix_still_matches(self):
        self.assertTrue(wares.image_for("Coca-Cola 0,5 l").endswith("coca-cola.png"))

    def test_specific_ware_beats_the_general_one(self):
        # "Faxe Kondi Booster Melon Boost" must not get the plain Faxe Kondi photo.
        self.assertTrue(
            wares.image_for("Faxe Kondi Booster Melon Boost").endswith("faxe-kondi-booster-melon-boost.png")
        )
        self.assertTrue(wares.image_for("Sport-Cola Light").endswith("sport-cola-light.png"))
        self.assertTrue(wares.image_for("Fuze Tea Fersken Hibiscus").endswith("fuze-tea-fersken-hibiscus.png"))

    def test_accents_do_not_matter(self):
        self.assertTrue(wares.image_for("Sport-Colá Light").endswith("sport-cola-light.png"))
        self.assertTrue(wares.image_for("Grimbergen Double Ambrée").endswith("grimbergen-double-ambree.png"))

    def test_unknown_product_has_no_image(self):
        self.assertEqual(wares.image_for("Ukendt vare"), "")
        self.assertEqual(wares.image_for(""), "")

    def test_every_listed_photo_exists(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parent.parent / "static" / "productdle" / "wares"
        for image, aliases in wares.WARES:
            self.assertTrue((root / image).is_file(), f"missing {image}")
            self.assertTrue(aliases, f"{image} has no names")


class ProductStatsImageTest(SimpleTestCase):
    def test_stats_carry_the_image(self):
        from .factories import make_product

        stats = logic.product_stats(make_product(name="Tuborg Grøn"))
        self.assertEqual(stats["image"], "/static/productdle/wares/tuborg-groen.png")
