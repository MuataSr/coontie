"""Today's order: severity decides what comes first, age decides inside a severity.

The findings here are written straight into the record's tables rather than walked through the CLI,
because the thing under test is the order of a list, and a stage arc would take minutes to produce the
same five rows.
"""

import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_lan_gate import Server  # noqa: E402

from coontie import inspect as inspection  # noqa: E402
from coontie.workspace import Facility, Room, Workspace  # noqa: E402

NOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)


def ago(**kwargs) -> str:
    return (NOW - timedelta(**kwargs)).isoformat()


class base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        self.ws = Workspace(self.db)
        self.ws.add_facility(Facility(id="f1", name="Cure Room Cultivation, LLC",
                                      license_number="MMTC-2026-0781", street="1 Grove Rd",
                                      city="Brooksville", state="FL", zip="34601"))
        self.ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
        # the catalogue is a DH5058 product record: fifteen columns, and no unit among them
        self.ws.conn.execute(
            "INSERT INTO products (id, facility_id, name, product_type, route, upid, created_at)"
            " VALUES ('p1','f1','Blue Dream 3.5g','Whole Flower','Smoking','UPID-0001',?)",
            (ago(days=30),))
        self.ws.conn.commit()
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.close()
        self.ws.close()
        self.tmp.cleanup()

    def stock_lot(self, lot_id: str, *, created: str, original: str = "100", moved: str | None = None):
        self.ws.conn.execute(
            "INSERT INTO stock_lots (id,kind,cultivar,room_id,original,unit,harvest_ids,source_lot_id,"
            "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (lot_id, "cured and dried flower", "Blue Dream", "inv1", original, "g", '["h1"]', "",
             created))
        if moved:
            self.ws.conn.execute(
                "INSERT INTO stock_moves (id,lot_id,kind,amount,unit,target_lot_id,note,at,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (f"mv-{lot_id}", lot_id, "extract", moved, "g", "", "", created, created))
        self.ws.conn.commit()

    def manifest(self, manifest_id: str, *, departed: str, status: str = "dispatched"):
        self.ws.conn.execute(
            "INSERT INTO manifests (id,facility_id,recipient_name,recipient_address,vehicle_id,"
            "employee_ids,departure_at,arrival_at,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (manifest_id, "f1", "Grove Dispensary", "2 Palm Ave", "veh-1", '["emp-1","emp-2"]',
             departed, "", status, departed))
        self.ws.conn.commit()

    def held_lot(self, lot_id: str, *, created: str):
        self.ws.conn.execute(
            "INSERT INTO lots (id,product_id,room_id,quantity,unit,on_hold,created_at,sts_inventory_id)"
            " VALUES (?,?,?,?,?,?,?,'')",
            (lot_id, "p1", "inv1", "40", "g", 1, created))
        self.ws.conn.commit()

    def expired_product(self, product_id: str, *, expired: str):
        self.ws.conn.execute(
            "INSERT INTO final_products (id,lot_id,upid,product_type,cultivar,unit_count,net_weight,"
            "unit,weight_per_unit,approved_name,packaged_at,expiration_date,room_id,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (product_id, "stk-1", "UPID-0001", "Whole Flower", "Blue Dream", 12, "42", "g", "3.5",
             "", expired, expired, "inv1", expired))
        self.ws.conn.commit()

    def findings(self):
        return inspection.inspect(self.ws, now=NOW)


class TestTheOrder(base):
    def seed_a_month(self):
        # two breaches, three weeks apart
        self.stock_lot("stk-old", created=ago(days=30), moved="120")
        self.stock_lot("stk-new", created=ago(days=1), moved="120")
        # three exposures: a manifest out three weeks, an expiry from yesterday, and a hold with no date
        self.manifest("man-1", departed=ago(days=21))
        self.expired_product("fp-1", expired=(NOW - timedelta(days=1)).date().isoformat())
        self.held_lot("lot-1", created=ago(days=2))

    def test_oldest_first_inside_a_severity(self):
        self.seed_a_month()
        found = self.findings()
        breaches = [f for f in found if f.severity == inspection.BREACH]
        self.assertEqual([f.subject for f in breaches], ["stk-old", "stk-new"],
                         "the older breach must lead even though its id sorts later")

    def test_severity_still_outranks_age(self):
        self.seed_a_month()
        found = self.findings()
        first_exposure = next(i for i, f in enumerate(found)
                              if f.severity == inspection.EXPOSURE)
        last_breach = max(i for i, f in enumerate(found) if f.severity == inspection.BREACH)
        self.assertLess(last_breach, first_exposure,
                        "a day-old breach precedes a three-week-old exposure")

    def test_an_undated_finding_sorts_last_in_its_severity(self):
        self.seed_a_month()
        found = self.findings()
        exposures = [f for f in found if f.severity == inspection.EXPOSURE]
        self.assertIsNone(exposures[-1].since)
        self.assertEqual(exposures[-1].code, "hold_unresolved")
        self.assertEqual([f.subject for f in exposures][:2], ["man-1", "fp-1"],
                         "the dated exposures are oldest first")
        notes = [f for f in found if f.severity == inspection.NOTE]
        if notes:
            self.assertGreater(found.index(notes[0]), found.index(exposures[-1]),
                               "an undated exposure still precedes every note")

    def test_the_order_is_stable(self):
        self.seed_a_month()
        first = [(f.code, f.subject) for f in self.findings()]
        second = [(f.code, f.subject) for f in self.findings()]
        self.assertEqual(first, second)

    def test_the_age_text_is_what_an_operator_reads(self):
        self.seed_a_month()
        by_subject = {f.subject: f for f in self.findings()}
        self.assertEqual(by_subject["stk-old"].age_text(NOW), "30 d")
        self.assertEqual(by_subject["man-1"].age_text(NOW), "21 d")
        self.assertEqual(by_subject["stk-new"].age_text(NOW), "1 d")
        self.assertEqual(by_subject["lot-1"].age_text(NOW), "—",
                         "no recorded date is a dash, not a guess")

    def test_audit_lists_them_in_the_same_order_as_the_list(self):
        import os
        import re as _re
        import subprocess

        self.seed_a_month()
        expected = [f.subject for f in self.findings() if f.subject]
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        result = subprocess.run([sys.executable, "-m", "coontie.cli", "--db", str(self.db), "audit"],
                                capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = [subject for subject in expected if subject in result.stdout]
        positions = [result.stdout.index(subject) for subject in seen]
        self.assertEqual(positions, sorted(positions),
                         "the printed audit must not order findings differently from the screen")
        self.assertGreaterEqual(len(seen), 3, result.stdout)

    def test_a_date_ahead_of_this_clock_is_a_dash_not_a_negative_age(self):
        future = (NOW + timedelta(days=2)).isoformat()
        self.manifest("man-future", departed=future)
        finding = next(f for f in self.findings() if f.subject == "man-future")
        self.assertIsNotNone(finding.since)
        self.assertEqual(finding.age_text(NOW), "—")


class TestTheScreen(base):
    def test_today_shows_an_age_a_dash_and_the_explanation(self):
        # the screen reads the real clock, so the fixture is written relative to it rather than to the
        # pinned NOW the ordering tests use
        real = datetime.now(timezone.utc)
        self.stock_lot("stk-old", created=(real - timedelta(days=30)).isoformat(), moved="120")
        self.manifest("man-1", departed=(real - timedelta(days=21)).isoformat())
        self.held_lot("lot-1", created=(real - timedelta(days=2)).isoformat())
        self.server = Server(self.db, lan=False)
        self.server.wait()
        status, body, _ = self.server.get("/")
        self.assertEqual(status, 200)
        self.assertIn("30 d old", body)
        self.assertIn("21 d old", body)
        self.assertIn("age unknown", body, "a dash with no words would read as punctuation")
        self.assertIn("Inside each severity the oldest is at the top", body)
        self.assertNotIn("record(s)", body, "a count and its plural are written, not abbreviated")
        self.assertRegex(body, r"\d+ of these carry no date this record can check")
        # the manifest's age must appear before the undated hold's row
        self.assertLess(body.index("21 d old"), body.index("still on hold"))

    def test_a_record_with_nothing_open_still_renders(self):
        self.server = Server(self.db, lan=False)
        self.server.wait()
        status, body, _ = self.server.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Nothing is open", body)


if __name__ == "__main__":
    unittest.main()


class TestTheWindowTitleSaysThePageName(unittest.TestCase):
    """The `<title>` said "Notes" while the page said "Today", because a loop rebound the heading."""

    def setUp(self):
        import tempfile
        from coontie.workspace import Facility, Room, Workspace

        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "ws.sqlite3"
        ws = Workspace(db)
        ws.add_facility(Facility(id="f1", name="Sand Pine Cultivation, LLC",
                                 license_number="MMTC-2026-0031", street="1 Grove Road",
                                 city="Brooksville", state="FL", zip="34601"))
        ws.add_room(Room(id="g1", facility_id="f1", kind="grow", name="G1", number="01"))
        ws.close()
        self.db = db

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_title_is_the_heading_not_the_last_severity_group(self):
        from coontie import web, theme

        app = web.App(self.db)
        ws = web.Workspace(self.db)
        try:
            html = app.render_today(ws, operator="Ana Ruiz")
        finally:
            ws.close()
        title = html.split("<title>", 1)[1].split(" · Coontie", 1)[0]
        heading = html.split("<h1>", 1)[1].split("</h1>", 1)[0]
        self.assertEqual(title, heading)
        for key in ("today.breaches", "today.exposures", "today.notes"):
            self.assertNotEqual(title, theme.say(app.voice, key),
                                "the window title must not carry a severity group's name")
