"""The five facility events the record was missing: people, API users, moves, destruction.

The interesting assertions are the ones about what is *not* stored: an API user's password never
reaches the ledger, a held lot never moves, and a lot cannot be destroyed inside the 72-hour wait.
"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from coontie import people
from coontie.events import BY_KEY, Stage
from coontie.workspace import Facility, Lot, Product, Room, Workspace

T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def workspace(path: Path) -> Workspace:
    ws = Workspace(path)
    ws.add_facility(Facility(id="f1", name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030"))
    ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="f1", kind="inventory", name="INV2", number="02"))
    ws.add_room(Room(id="g1", facility_id="f1", kind="grow", name="G1", number="03"))
    product, _ = ws.add_product(Product(
        id="p1", facility_id="f1", name="Blue Dream 3.5g", product_type="Whole Flower",
        route="Smoking", upid="blue-dream-3.5-smoking-DE1114", weight_g=None, cultivar="Blue Dream",
    ))
    ws.add_lot(Lot(id="lot-1", product_id=product.id, room_id="inv1", quantity=Decimal("35"), unit="g"))
    return ws


def payload_of(ws: Workspace, key: str) -> dict:
    row = ws.conn.execute(
        "SELECT payload FROM events WHERE event_key = ? ORDER BY rowid DESC LIMIT 1", (key,)
    ).fetchone()
    return json.loads(row["payload"])


class TestPeople(unittest.TestCase):
    def test_an_employee_is_recorded_with_the_catalogues_four_fields(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            employee = ws.add_employee(full_name="Maria  Lopez", date_of_birth="1990-04-02",
                                       hire_date="2026-01-05", email="Maria@Example.com")
            self.assertEqual(employee.email, "maria@example.com")
            self.assertEqual(employee.full_name, "Maria Lopez")
            payload = payload_of(ws, "employee_record")
            for field in ("full_name", "dob", "hire_date", "email"):
                self.assertIn(field, payload)
            self.assertEqual(payload["dob"], "1990-04-02")
            ws.close()

    def test_a_second_record_for_the_same_person_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.add_employee(full_name="Maria Lopez", date_of_birth="1990-04-02",
                            hire_date="2026-01-05", email="maria@example.com")
            with self.assertRaises(ValueError) as ctx:
                ws.add_employee(full_name="Maria Lopez", date_of_birth="1990-04-02",
                                hire_date="2026-01-05", email="MARIA@example.com")
            self.assertIn("already an employee", str(ctx.exception))
            ws.close()

    def test_a_birth_date_after_the_hire_date_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            with self.assertRaises(ValueError) as ctx:
                ws.add_employee(full_name="Maria Lopez", date_of_birth="2027-01-01",
                                hire_date="2026-01-05", email="maria@example.com")
            self.assertIn("not before the hire date", str(ctx.exception))
            ws.close()

    def test_one_word_is_not_a_full_name(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            with self.assertRaises(ValueError) as ctx:
                ws.add_employee(full_name="Maria", date_of_birth="1990-04-02",
                                hire_date="2026-01-05", email="maria@example.com")
            self.assertIn("full name", str(ctx.exception))
            ws.close()


class TestApiUsers(unittest.TestCase):
    def test_the_password_never_reaches_the_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            ws = workspace(db)
            secret = "correct horse battery staple"
            ws.add_api_user(email="robot@example.com", password=secret,
                            permissions="inventory.read, transport.write")
            payload = payload_of(ws, "api_user")
            self.assertEqual(payload["email"], "robot@example.com")
            self.assertEqual(payload["permissions"], ["inventory.read", "transport.write"])
            self.assertIn("password_verifier", payload)
            self.assertIn("verifier only", payload["password_note"])
            self.assertNotIn("password", payload)
            ws.close()

            # and not anywhere in the file, not just in the payload we looked at
            raw = db.read_bytes()
            self.assertNotIn(secret.encode(), raw, "the plaintext password is in the database file")

    def test_the_verifier_checks_the_password_and_rejects_a_wrong_one(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.add_api_user(email="robot@example.com", password="correct horse battery",
                            permissions="inventory.read")
            encoded = ws.conn.execute("SELECT verifier FROM api_users").fetchone()[0]
            self.assertTrue(people.verify("correct horse battery", encoded))
            self.assertFalse(people.verify("correct horse batter", encoded))
            ws.close()

    def test_a_short_password_and_an_empty_permission_list_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            with self.assertRaises(ValueError):
                ws.add_api_user(email="robot@example.com", password="short", permissions="x")
            with self.assertRaises(ValueError) as ctx:
                ws.add_api_user(email="robot@example.com", password="long enough password",
                                permissions="  ")
            self.assertIn("permissions", str(ctx.exception))
            ws.close()

    def test_an_adjustment_carries_every_field_the_catalogue_requires(self):
        """The soak found this: a correction payload was missing inventory_id, a required field.

        Stage modules were checked against the catalogue from S5 onward; corrections were not, so
        every adjustment the record ever wrote would have been unreadable to the department.
        """
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            try:
                ws.amend_lot("lot-1", new_quantity=Decimal("32"), cause="miscount",
                             reason="Physical recount", actor="Maria Lopez", when=T0)
                entry = ws.ledger.latest("inventory_adjustment")
                self.assertIsNotNone(entry)
                payload = entry.payload
                spec = BY_KEY["inventory_adjustment"]
                for field in spec.fields:
                    if field.required:
                        self.assertIn(field.name, payload,
                                      f"{field.name} is required by DH5059 and missing from the payload")
                # the lot has no department id, so the record says which id it wrote
                self.assertEqual(payload["inventory_id"], "lot-1")
                self.assertEqual(payload["inventory_id_source"], "local")
                self.assertEqual(payload["inventory_reference"], "lot-1")
            finally:
                ws.close()

    def test_the_password_field_is_the_only_catalog_field_the_record_rewrites(self):
        """The exception is declared, not silent: this test names the one field and why."""
        spec = BY_KEY["api_user"]
        names = {field.name for field in spec.fields}
        self.assertEqual(names, {"email", "password", "permissions"})
        recorded = {"email", "permissions", "password_verifier"}
        self.assertEqual(
            names - recorded, {"password"},
            "the catalogue's password field is deliberately recorded as a verifier; if another "
            "field is added to the catalogue, this test must be revisited",
        )
        self.assertIs(BY_KEY["api_user"].stage, Stage.ADMIN)


class TestInventoryMove(unittest.TestCase):
    def test_a_lot_moves_between_rooms_and_the_event_names_both(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            lot = ws.move_inventory("lot-1", "INV2", note="making room for a delivery", at=T0)
            self.assertEqual(lot.room_id, "inv2")
            payload = payload_of(ws, "inventory_move")
            self.assertEqual(payload["facility_location"], "inv1")
            self.assertEqual(payload["inventory_ids"], ["lot-1"])
            self.assertEqual(payload["to_room"], "inv2")
            self.assertEqual(payload["quantity"], "35")
            ws.close()

    def test_a_move_to_the_room_it_already_sits_in_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            with self.assertRaises(ValueError) as ctx:
                ws.move_inventory("lot-1", "INV1")
            self.assertIn("already in INV1", str(ctx.exception))
            ws.close()

    def test_a_held_lot_does_not_move(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.conn.execute("UPDATE lots SET on_hold = 1 WHERE id = 'lot-1'")
            ws.conn.commit()
            with self.assertRaises(ValueError) as ctx:
                ws.move_inventory("lot-1", "INV2")
            self.assertIn("on hold", str(ctx.exception))
            self.assertEqual(ws.lot("lot-1").room_id, "inv1")
            ws.close()

    def test_an_ambiguous_prefix_is_refused_rather_than_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.add_lot(Lot(id="lot-2", product_id="p1", room_id="inv1", quantity=Decimal("10"), unit="g"))
            with self.assertRaises(ValueError) as ctx:
                ws.lot("lot-")
            self.assertIn("matches 2 lots", str(ctx.exception))
            self.assertEqual(ws.lot("lot-2").id, "lot-2")
            ws.close()


class TestInventoryDisposal(unittest.TestCase):
    def test_destruction_needs_a_schedule_and_the_72_hour_wait(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            with self.assertRaises(ValueError) as ctx:
                ws.dispose_lot("lot-1", at=T0)
            self.assertIn("schedule first", str(ctx.exception))

            ws.schedule_disposal_lot("lot-1", reason="failed potency test", at=T0)
            # inside the wait, by one hour
            with self.assertRaises(ValueError) as ctx:
                ws.dispose_lot("lot-1", at=T0 + timedelta(hours=71))
            self.assertIn("1h remain", str(ctx.exception))
            # exactly at the boundary is enough
            done = ws.dispose_lot("lot-1", at=T0 + timedelta(hours=72))
            self.assertIsNotNone(done.disposed_at)
            ws.close()

    def test_the_lot_row_stays_and_its_quantity_goes_to_zero(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.schedule_disposal_lot("lot-1", reason="contamination", at=T0)
            disposal = ws.dispose_lot("lot-1", at=T0 + timedelta(hours=72))
            lot = ws.lot("lot-1")
            self.assertEqual(Decimal(lot.quantity), Decimal("0"))
            self.assertEqual(Decimal(disposal.weight), Decimal("35"))
            payload = payload_of(ws, "disposal_inventory")
            self.assertEqual(payload["inventory_id"], "lot-1")
            self.assertEqual(payload["weight"], "35")
            ws.close()

    def test_a_destroyed_lot_cannot_move_or_be_destroyed_again(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.schedule_disposal_lot("lot-1", reason="contamination", at=T0)
            ws.dispose_lot("lot-1", at=T0 + timedelta(hours=72))
            with self.assertRaises(ValueError):
                ws.move_inventory("lot-1", "INV2")
            with self.assertRaises(ValueError) as ctx:
                ws.schedule_disposal_lot("lot-1", reason="again", at=T0)
            self.assertIn("nothing to destroy", str(ctx.exception))
            ws.close()

    def test_a_second_schedule_for_the_same_lot_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.schedule_disposal_lot("lot-1", reason="failed potency test", at=T0)
            with self.assertRaises(ValueError) as ctx:
                ws.schedule_disposal_lot("lot-1", reason="failed potency test", at=T0)
            self.assertIn("already scheduled", str(ctx.exception))
            ws.close()


class TestCatalogCoverage(unittest.TestCase):
    def test_the_five_events_carry_the_catalogues_required_fields(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d) / "ws.sqlite3")
            ws.add_employee(full_name="Maria Lopez", date_of_birth="1990-04-02",
                            hire_date="2026-01-05", email="maria@example.com")
            ws.add_api_user(email="robot@example.com", password="correct horse battery",
                            permissions="inventory.read")
            ws.move_inventory("lot-1", "INV2", at=T0)
            ws.schedule_disposal_lot("lot-1", reason="contamination", at=T0)
            ws.dispose_lot("lot-1", at=T0 + timedelta(hours=72))

            written = {row["event_key"] for row in ws.conn.execute("SELECT event_key FROM events")}
            for key in ("employee_record", "api_user", "inventory_move",
                        "disposal_schedule_inventory", "disposal_inventory"):
                self.assertIn(key, written, key)
                payload = payload_of(ws, key)
                for field in BY_KEY[key].fields:
                    if field.name == "password" and key == "api_user":
                        self.assertIn("password_verifier", payload)
                        continue
                    self.assertIn(
                        field.name, payload,
                        f"{key} is missing the department's field {field.name!r}: {sorted(payload)}",
                    )
            ws.close()

    def test_no_catalog_event_is_left_unwritten(self):
        """The coverage claim, as a test: every DH5059 key is appended by something."""
        src = "\n".join(p.read_text() for p in (Path(__file__).resolve().parents[1] / "src" / "coontie").glob("*.py"))
        import re

        appended = set(re.findall(r"ledger\.append\(\s*[\"']([a-z_]+)[\"']", src))
        # room creation and integration append their key from a variable, not a literal
        appended |= {"grow_room_create", "inventory_room_create"}
        mmur_blocked = {"refund", "void_sale"}
        missing = sorted(set(BY_KEY) - appended - mmur_blocked)
        self.assertEqual(
            missing, [],
            f"these catalogue events have no writer yet: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
