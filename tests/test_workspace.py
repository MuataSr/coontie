"""The workspace: master data, lots, and a ledger that agrees with them."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from coontie.workspace import Facility, Lot, Product, Room, Workspace


def make_ws(tmp: Path) -> Workspace:
    ws = Workspace(tmp / "test.sqlite3")
    ws.add_facility(Facility(id="f1", name="Nature's Grace", license_number="MMTC-2026-0030"))
    ws.add_room(Room(id="r1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="r2", facility_id="f1", kind="grow", name="G1", number="02"))
    return ws


def product(upid="BD-1", name="Blue Dream 3.5g") -> Product:
    return Product(
        id="p1", facility_id="f1", name=name, product_type="Whole Flower", route="Smoking",
        upid=upid, weight_g=Decimal("3.5"), cultivar="Blue Dream",
    )


class TestSetup(unittest.TestCase):
    def test_facility_and_rooms(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            self.assertEqual(ws.facility().name, "Nature's Grace")
            self.assertEqual(len(ws.rooms()), 2)
            ws.close()

    def test_product_dedupe_by_upid(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            _, created = ws.add_product(product())
            self.assertTrue(created)
            existing, created_again = ws.add_product(product("BD-1", "Blue Dream (other name)"))
            self.assertFalse(created_again)
            self.assertEqual(existing.name, "Blue Dream 3.5g")
            self.assertEqual(len(ws.products()), 1)
            ws.close()

    def test_lot_and_inventory_join(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            ws.add_product(product())
            ws.add_lot(Lot(id="l1", product_id="p1", room_id="r1", quantity=Decimal("120"), unit="g"))
            rows = ws.inventory()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["room"], "INV1")
            self.assertEqual(rows[0]["quantity"], "120")
            ws.close()

    def test_ledger_verifies_after_writes(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            ws.add_product(product())
            ws.add_lot(Lot(id="l1", product_id="p1", room_id="r1", quantity=Decimal("10"), unit="g"))
            ok, summary = ws.verify()
            self.assertTrue(ok, summary)
            self.assertIn("1 products", summary)
            ws.close()

    def test_ledger_records_each_creation(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            ws.add_product(product())
            keys = [e.event_key for e in ws.ledger.entries()]
            self.assertEqual(keys[0], "facility_registered")
            self.assertIn("inventory_room_create", keys)
            self.assertIn("grow_room_create", keys)
            self.assertIn("product_catalogue_add", keys)
            ws.close()

    def test_duplicate_room_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ws = make_ws(Path(d))
            with self.assertRaises(Exception):
                ws.add_room(Room(id="r3", facility_id="f1", kind="inventory", name="INV1", number="01"))
            ws.close()


if __name__ == "__main__":
    unittest.main()
