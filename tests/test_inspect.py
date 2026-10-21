"""The inspection simulator: findings from the record's own rows, and the same answer twice."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from coontie.inspect import BREACH, EXPOSURE, NOTE, inspect, summarize
from coontie.workspace import Facility, Room, Workspace

T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)
LATER = T0 + timedelta(days=2)
ROOMS = [("inventory", "INV1", "01")]


def workspace(root: Path) -> Workspace:
    ws = Workspace(root / "ws.sqlite3")
    ws.add_facility(Facility(id="f1", name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030"))
    ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    return ws


def lot(ws: Workspace, weight="500", kind="cured and dried flower"):
    return ws.new_lot(kind=kind, cultivar="Blue Dream", weight=weight, room="inv1", at=T0)


class TestCleanRecord(unittest.TestCase):
    def test_a_clean_record_has_no_breaches_or_exposures(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            lot(ws)
            findings = inspect(ws, now=LATER)
            self.assertEqual([f for f in findings if f.severity != NOTE], [])
            ws.close()


class TestJustifications(unittest.TestCase):
    def test_an_amendment_with_no_justification_is_a_breach(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            amendment, justification = ws.adjust_stock(stock.id, remove="2", cause="spillage",
                                                       reason="jar knocked over", at=T0)
            self.assertIsNotNone(justification)
            ws.conn.execute("DELETE FROM justifications WHERE id = ?", (justification.id,))
            ws.conn.commit()
            codes = [f.code for f in inspect(ws, now=LATER)]
            self.assertIn("justification_missing", codes)
            ws.close()

    def test_an_unsent_justification_past_its_deadline_is_a_breach(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            _a, justification = ws.adjust_stock(stock.id, remove="2", cause="spillage",
                                                reason="jar knocked over", at=T0)
            findings = [f for f in inspect(ws, now=justification.deadline + timedelta(hours=1))
                        if f.code == "justification_unsent"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, BREACH)
            self.assertIn("64-4.222(12)", findings[0].citation)
            ws.close()

    def test_a_late_send_is_an_exposure_not_a_breach(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            _a, justification = ws.adjust_stock(stock.id, remove="2", cause="spillage",
                                                reason="jar knocked over", at=T0)
            ws.conn.execute("UPDATE justifications SET sent_at = ? WHERE id = ?",
                            ((justification.deadline + timedelta(hours=3)).isoformat(), justification.id))
            ws.conn.commit()
            findings = [f for f in inspect(ws, now=justification.deadline + timedelta(hours=4))
                        if f.code == "justification_late"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, EXPOSURE)
            ws.close()

    def test_an_exempt_correction_produces_no_finding(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            amendment, justification = ws.adjust_stock(stock.id, remove="2", cause="processing",
                                                       reason="loss in conversion", at=T0)
            self.assertTrue(amendment.exempt)
            self.assertIsNone(justification)
            codes = [f.code for f in inspect(ws, now=LATER)]
            self.assertNotIn("justification_missing", codes)
            ws.close()


class TestInventoryAndTransport(unittest.TestCase):
    def test_an_expired_final_product_is_an_exposure(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            ws.conn.execute(
                "INSERT INTO final_products (id,lot_id,upid,product_type,cultivar,unit_count,net_weight,unit,"
                "weight_per_unit,approved_name,packaged_at,expiration_date,room_id,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("fin-1", stock.id, "upid-1", "Whole Flower", "Blue Dream", 10, "35", "g", None, "Blue Dream",
                 "2026-01-01T00:00:00+00:00", "2026-02-01", "inv1", T0.isoformat()),
            )
            ws.conn.commit()
            findings = [f for f in inspect(ws, now=LATER) if f.code == "expired_available"]
            self.assertEqual(len(findings), 1)
            self.assertIn("2026-02-01", findings[0].summary)
            ws.close()

    def test_a_dispatch_with_no_receipt_is_an_exposure(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            vehicle = ws.register_vehicle(name="Van", plate="FL-1", make="Ford", model="Transit")
            manifest = ws.build_manifest(
                recipient_name="Tampa Dispensary", recipient_address="900 N Tampa St",
                vehicle=vehicle.id, employee_ids=("Maria Lopez", "Dev Patel"),
                departure_at=T0, arrival_at=T0 + timedelta(hours=3),
                items=[(stock.id, "100", "")], at=T0,
            )
            ws.dispatch_manifest(manifest.id, at=T0)
            findings = [f for f in inspect(ws, now=LATER) if f.code == "manifest_unreceived"]
            self.assertEqual(len(findings), 1)
            self.assertIn("381.986(8)(g)", findings[0].citation)
            ws.close()

    def test_moves_in_another_unit_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            ws.conn.execute(
                "INSERT INTO stock_moves (id,lot_id,kind,amount,unit,target_lot_id,note,at,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("mov-1", stock.id, "ingredient", "0", "ml", "", "", T0.isoformat(), T0.isoformat()),
            )
            ws.conn.commit()
            findings = [f for f in inspect(ws, now=LATER) if f.code == "stock_unit_mismatch"]
            self.assertEqual(len(findings), 1)
            self.assertIn("ml", findings[0].summary)
            ws.close()

    def test_an_empty_workspace_reports_the_limitations_not_a_pass(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            from coontie.inspect import CANNOT_CHECK

            self.assertTrue(CANNOT_CHECK)
            self.assertTrue(any("MMUR" in c.why for c in CANNOT_CHECK))
            ws.close()


class TestDeterminism(unittest.TestCase):
    def test_the_same_record_gives_the_same_findings_twice(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            ws.adjust_stock(stock.id, remove="2", cause="spillage", reason="jar knocked over", at=T0)
            first = json.dumps([f.line() for f in inspect(ws, now=LATER)], sort_keys=True)
            second = json.dumps([f.line() for f in inspect(ws, now=LATER)], sort_keys=True)
            self.assertEqual(first, second)
            counts = summarize(inspect(ws, now=LATER))
            self.assertEqual(set(counts), {BREACH, EXPOSURE, NOTE})
            ws.close()

    def test_breaches_come_before_exposures_in_the_listing(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            stock = lot(ws)
            _a, justification = ws.adjust_stock(stock.id, remove="2", cause="spillage",
                                                reason="jar knocked over", at=T0)
            findings = inspect(ws, now=justification.deadline + timedelta(hours=1))
            severities = [f.severity for f in findings]
            self.assertEqual(severities, sorted(severities, key=lambda s: {BREACH: 0, EXPOSURE: 1, NOTE: 2}[s]))
            ws.close()


if __name__ == "__main__":
    unittest.main()
