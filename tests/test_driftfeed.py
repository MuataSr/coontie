"""Reading the department's export: aliases, units, statuses, and refusals."""

import unittest
from decimal import Decimal

from coontie.driftfeed import normalise_status, normalise_unit, parse_state_export, to_base

HEADERS = "Inventory ID,Product Name,Quantity,UOM,Status,Room\n"


class TestAliases(unittest.TestCase):
    def test_the_form_style_headers_work(self):
        text = (
            "Inventory Identification Number,Item Name,Weight,UOM,Inventory Status,Location\n"
            "FL-1,Blue Dream,3.5,g,Active,INV1\n"
        )
        parsed = parse_state_export(text)
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.rows[0].sts_inventory_id, "FL-1")
        self.assertEqual(parsed.rows[0].quantity, Decimal("3.5"))
        self.assertEqual(parsed.rows[0].status, "active")

    def test_short_headers_work(self):
        parsed = parse_state_export(HEADERS + "FL-1,Blue Dream,10,g,On Hold,INV1\n")
        self.assertEqual(parsed.rows[0].status, "on_hold")

    def test_missing_id_column_is_refused(self):
        parsed = parse_state_export("Product,Qty\nexample,5\n")
        self.assertEqual(parsed.rows, ())
        self.assertIn("no inventory id", parsed.rejected[0][1])

    def test_bad_quantity_is_reported_with_its_line(self):
        parsed = parse_state_export(HEADERS + "FL-1,Blue Dream,many,g,Active,INV1\n")
        self.assertEqual(parsed.rows, ())
        self.assertEqual(parsed.rejected[0][0], 2)
        self.assertIn("not a number", parsed.rejected[0][1])

    def test_unclaimed_columns_are_listed(self):
        parsed = parse_state_export(HEADERS + "FL-1,Blue Dream,10,g,Active,INV1\n" )
        self.assertIn("Notes", parse_state_export(
            "Inventory ID,Product Name,Quantity,UOM,Status,Room,Notes\nFL-1,X,1,g,Active,INV1,hi\n"
        ).unmapped)


class TestStatuses(unittest.TestCase):
    def test_known_statuses(self):
        cases = {
            "Active": "active", "ACTIVE": "active", "on hold": "on_hold", "ONHOLD": "on_hold",
            "Quarantine": "on_hold", "Sold": "sold", "Dispensed": "sold", "Void": "inactive",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalise_status(raw), expected, raw)

    def test_unknown_status_is_passed_through_not_guessed(self):
        self.assertEqual(normalise_status("Needs Review"), "needs review")


class TestUnits(unittest.TestCase):
    def test_grams_and_ounces(self):
        self.assertEqual(to_base("60", "g"), (Decimal("60"), "g"))
        grams, unit = to_base("2.117", "oz")
        self.assertEqual(unit, "g")
        self.assertAlmostEqual(float(grams), 60.0, places=1)

    def test_milligrams_become_grams(self):
        self.assertEqual(to_base("500", "mg"), (Decimal("0.5"), "g"))

    def test_counts_are_not_converted(self):
        self.assertEqual(to_base("12", "each"), (Decimal("12"), "units"))

    def test_alias_units(self):
        self.assertEqual(normalise_unit("Grams"), "g")
        self.assertEqual(normalise_unit("OUNCES"), "oz")
        self.assertEqual(normalise_unit("ml"), "ml")


if __name__ == "__main__":
    unittest.main()
