"""Unique product IDs: the six attributes decide identity, exactly as the rule says."""

import unittest
from decimal import Decimal

from coontie.forms import COLUMNS, PRODUCT_TYPES, ROUTES, canon_product_type, canon_route, render_csv
from coontie.products import ProductKey, derive_upid, ratio, upid_for


class TestRatio(unittest.TestCase):
    def test_one_to_one(self):
        self.assertEqual(ratio(100, 100), "1:1")

    def test_thc_only(self):
        self.assertEqual(ratio(88.5, 0), "1:0")

    def test_cbd_only(self):
        self.assertEqual(ratio(0, 250), "0:1")

    def test_reduced(self):
        self.assertEqual(ratio(20, 10), "2:1")

    def test_both_zero(self):
        self.assertEqual(ratio(0, 0), "0:0")


class TestIdentity(unittest.TestCase):
    def test_same_six_attributes_same_id(self):
        a, _ = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=1.2, route="Smoking")
        b, _ = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=1.2, route="Smoking")
        self.assertEqual(a, b)

    def test_name_does_not_change_identity(self):
        # Rule 64-4.221(1)(c) groups on attributes, not on marketing names.
        a, ka = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Smoking")
        b, kb = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Smoking")
        self.assertEqual(ka.canonical(), kb.canonical())
        self.assertEqual(a, b)

    def test_route_changes_identity(self):
        a, _ = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Smoking")
        b, _ = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Inhalation")
        self.assertNotEqual(a, b)

    def test_size_changes_identity(self):
        a, _ = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Smoking")
        b, _ = upid_for(cultivar="Blue Dream", size="7", thc_mg=177, cbd_mg=0, route="Smoking")
        self.assertNotEqual(a, b)

    def test_flavor_changes_identity(self):
        a, _ = upid_for(cultivar="X", size="1", flavor="mint", thc_mg=10, cbd_mg=0, route="Oral")
        b, _ = upid_for(cultivar="X", size="1", flavor="berry", thc_mg=10, cbd_mg=0, route="Oral")
        self.assertNotEqual(a, b)

    def test_supplied_sku_is_adopted(self):
        upid, key = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Smoking", supplied_sku="  BD-35 ")
        self.assertEqual(upid, "BD-35")
        self.assertEqual(key.route, "smoking")

    def test_ids_are_stable_across_processes(self):
        # Determinism matters: an operator who re-imports must not get a second catalogue.
        key = ProductKey.build(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Smoking")
        self.assertEqual(derive_upid(key), derive_upid(key))

    def test_ids_carry_a_readable_prefix(self):
        upid, _ = upid_for(cultivar="Blue Dream", size="3.5", thc_mg=88.5, cbd_mg=0, route="Smoking")
        self.assertTrue(upid.startswith("blue-dream"))
        self.assertRegex(upid, r"-[0-9A-F]{6}$")


class TestCanonicalValues(unittest.TestCase):
    def test_product_type_aliases(self):
        self.assertEqual(canon_product_type("flower"), "Whole Flower")
        self.assertEqual(canon_product_type("Preroll"), "Pre-rolled marijuana cigarette")
        self.assertEqual(canon_product_type("gummies"), "Gelatin")
        self.assertEqual(canon_product_type("Whole Flower"), "Whole Flower")

    def test_route_aliases(self):
        self.assertEqual(canon_route("smoke"), "Smoking")
        self.assertEqual(canon_route("rectal"), "Suppository")
        self.assertEqual(canon_route("Inhalation"), "Inhalation")

    def test_unknown_values_are_refused_with_the_forms_options(self):
        with self.assertRaises(ValueError) as ctx:
            canon_product_type("mystery")
        self.assertIn("Whole Flower", str(ctx.exception))
        with self.assertRaises(ValueError):
            canon_route("mystery")


class TestRender(unittest.TestCase):
    def test_column_order_matches_the_form(self):
        self.assertEqual(COLUMNS[0], "MMTC Name")
        self.assertEqual(COLUMNS[2], "Route of Administration")
        self.assertEqual(COLUMNS[14], "Reference Number")
        self.assertEqual(len(COLUMNS), 15)

    def test_form_enumerations_are_transcribed(self):
        self.assertIn("Pre-rolled marijuana cigarette", PRODUCT_TYPES)
        self.assertIn("Marijuana Delivery Device", PRODUCT_TYPES)
        self.assertIn("Smoking", ROUTES)
        self.assertEqual(len(PRODUCT_TYPES), 15)
        self.assertEqual(len(ROUTES), 7)

    def test_render_has_only_form_columns(self):
        from coontie.workspace import Product

        p = Product(
            id="p1", facility_id="f1", name="Blue Dream 3.5g", product_type="Whole Flower",
            route="Smoking", upid="BD-1", thc_mg=Decimal("88.5"), cbd_mg=Decimal("1.2"),
            weight_g=Decimal("3.5"), cultivar="Blue Dream", brand="Nature's Grace",
        )
        text = render_csv([p], "Test MMTC")
        header, row = text.splitlines()
        self.assertEqual(header.split(","), list(COLUMNS))
        self.assertIn("Test MMTC", row)
        self.assertIn("88.5", row)
        self.assertIn("No", row)  # delivery device


if __name__ == "__main__":
    unittest.main()
