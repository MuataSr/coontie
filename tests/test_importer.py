"""Import: forgiving on headers, strict on values, honest in the report."""

import tempfile
import unittest
from pathlib import Path

from coontie.importer import import_csv, map_headers
from coontie.workspace import Facility, Room, Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "operator_export.csv"


def make_ws(tmp: Path) -> Workspace:
    ws = Workspace(tmp / "w.sqlite3")
    ws.add_facility(Facility(id="f1", name="Nature's Grace", license_number="MMTC-2026-0030"))
    ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="f1", kind="inventory", name="INV2", number="02"))
    return ws


class TestHeaderMapping(unittest.TestCase):
    def test_loose_headers_land_in_canonical_fields(self):
        mapping, unmapped = map_headers(["Item Name", "Category", "Route", "Strain", "Brand", "THC (mg)", "On Hand", "UOM"])
        self.assertEqual(mapping["product_name"], "Item Name")
        self.assertEqual(mapping["product_type"], "Category")
        self.assertEqual(mapping["route"], "Route")
        self.assertEqual(mapping["cultivar"], "Strain")
        self.assertEqual(mapping["thc_mg"], "THC (mg)")
        self.assertEqual(mapping["quantity"], "On Hand")
        self.assertEqual(mapping["unit"], "UOM")
        self.assertEqual(unmapped, [])

    def test_form_headers_map_too(self):
        mapping, _ = map_headers(["MMTC Name", "Product Type", "Route of Administration", "Unique Product ID"])
        self.assertEqual(mapping["mmtc_name"], "MMTC Name")
        self.assertEqual(mapping["upid"], "Unique Product ID")

    def test_unknown_columns_are_reported_not_swallowed(self):
        _, unmapped = map_headers(["Item Name", "Zebra Column"])
        self.assertIn("Zebra Column", unmapped)


class TestDryRun(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            before = ws.verify()
            report = import_csv(ws, FIXTURE, facility_id="f1", dry_run=True)
            self.assertTrue(report.dry_run)
            self.assertEqual(ws.products(), [])
            self.assertEqual(ws.verify(), before)
            self.assertGreater(report.rows_ok, 0)
            ws.close()


class TestRealImport(unittest.TestCase):
    def test_import_creates_catalogue_and_lots(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            report = import_csv(ws, FIXTURE, facility_id="f1")
            self.assertEqual(report.rows_total, 9)
            self.assertEqual(report.rows_failed, 2)
            self.assertEqual(report.rows_ok, 7)
            self.assertEqual(report.products_created, 5)
            self.assertEqual(report.lots_created, 7)
            self.assertEqual(len(ws.products()), 5)
            self.assertEqual(len(ws.inventory()), 7)
            ws.close()

    def test_duplicate_rows_collapse_into_one_product(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            import_csv(ws, FIXTURE, facility_id="f1")
            blue = [p for p in ws.products() if p.name.startswith("Blue Dream 3.5g")]
            self.assertEqual(len(blue), 1)
            lots = [l for l in ws.lots() if l.product_id == blue[0].id]
            self.assertEqual(len(lots), 2)
            ws.close()

    def test_bad_rows_are_reported_with_line_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            report = import_csv(ws, FIXTURE, facility_id="f1")
            messages = " ".join(m for _, m in report.errors)
            self.assertIn("mystery", messages.lower())
            self.assertIn("not a number", messages.lower())
            self.assertEqual([line for line, _ in report.errors], [8, 9])
            ws.close()

    def test_reimport_is_idempotent_for_products(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            first = import_csv(ws, FIXTURE, facility_id="f1")
            self.assertEqual(first.products_created, 5)
            self.assertEqual(first.products_reused, 2)  # the two in-file duplicates
            second = import_csv(ws, FIXTURE, facility_id="f1")
            self.assertEqual(second.products_created, 0)
            self.assertEqual(second.products_reused, 7)  # every row matched an existing product
            self.assertEqual(len(ws.products()), 5)
            ws.close()

    def test_ledger_still_verifies_after_import(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            import_csv(ws, FIXTURE, facility_id="f1")
            ok, summary = ws.verify()
            self.assertTrue(ok, summary)
            ws.close()

    def test_import_batch_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            report = import_csv(ws, FIXTURE, facility_id="f1")
            row = ws.conn.execute("SELECT * FROM import_batches WHERE id = ?", (report.batch_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["rows_ok"], 7)
            ws.close()


if __name__ == "__main__":
    unittest.main()
