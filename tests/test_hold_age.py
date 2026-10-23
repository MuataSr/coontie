"""A hold has a date, so a held lot can be aged instead of dashed.

Three writers can put a lot on hold, so all three are tested here: creation, the incumbent import, and
the amendment a person makes. The fourth case is the one that matters most: a record written before the
column existed must gain it and keep its held lot undated rather than inheriting a guess.
"""

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from coontie import inspect as inspection  # noqa: E402
from coontie.workspace import Facility, Lot, Room, Workspace  # noqa: E402

NOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)


class base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        self.ws = Workspace(self.db)
        self.ws.add_facility(Facility(id="f1", name="Cure Room Cultivation, LLC",
                                      license_number="MMTC-2026-0781", street="1 Grove Rd",
                                      city="Brooksville", state="FL", zip="34601"))
        self.ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
        self.ws.conn.execute(
            "INSERT INTO products (id,facility_id,name,product_type,route,upid,created_at)"
            " VALUES ('p1','f1','Blue Dream 3.5g','Whole Flower','Smoking','UPID-0001',?)",
            (NOW.isoformat(),))
        self.ws.conn.commit()

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def lot(self, lot_id="lot-1", *, on_hold=False):
        self.ws.add_lot(Lot(id=lot_id, product_id="p1", room_id="inv1", quantity="40", unit="g",
                            on_hold=on_hold))
        return lot_id

    def held_findings(self):
        return [f for f in inspection.inspect(self.ws, now=NOW) if f.code == "hold_unresolved"]

    def held_at(self, lot_id="lot-1"):
        return self.ws.conn.execute("SELECT held_at FROM lots WHERE id = ?", (lot_id,)).fetchone()[0]


class TestAHoldHasADate(base):
    def test_a_lot_created_on_hold_is_dated_at_creation(self):
        self.lot(on_hold=True)
        self.assertTrue(self.held_at())
        finding = self.held_findings()[0]
        self.assertIsNotNone(finding.since, "a hold written by this build must carry its own moment")

    def test_a_lot_created_free_has_no_date_until_it_is_held(self):
        self.lot(on_hold=False)
        self.assertEqual(self.held_at(), "")
        self.assertEqual(self.held_findings(), [])
        self.ws.amend_lot("lot-1", new_on_hold=True, cause="contamination", reason="mold found",
                          when=NOW - timedelta(days=4))
        self.assertEqual(self.held_at(), (NOW - timedelta(days=4)).isoformat())
        finding = self.held_findings()[0]
        self.assertEqual(finding.age_text(NOW), "4 d")

    def test_releasing_clears_the_date_and_the_finding(self):
        self.lot(on_hold=False)
        self.ws.amend_lot("lot-1", new_on_hold=True, cause="contamination", reason="mold found",
                          when=NOW - timedelta(days=4))
        self.assertEqual(len(self.held_findings()), 1)
        self.ws.amend_lot("lot-1", new_on_hold=False, cause="contamination", reason="retested clean",
                          when=NOW)
        self.assertEqual(self.held_at(), "", "a released lot is not a lot with a stale date")
        self.assertEqual(self.held_findings(), [])

    def test_adopting_the_states_held_lot_dates_the_hold_it_creates(self):
        """The second writer is drift resolution: adopting a lot the export holds puts it on hold here."""
        self.ws.conn.execute(
            "INSERT INTO state_snapshots (id, source_file, as_of, rows, rejected, created_at)"
            " VALUES ('snap-1','export.csv',?,2,0,?)", (NOW.isoformat(), NOW.isoformat()))
        self.ws.conn.execute(
            "INSERT INTO drift_findings (id,snapshot_id,kind,record_key,ours,theirs,note,resolution,"
            "resolution_note,resolved_at,created_at) VALUES ('drf-1','snap-1','missing_locally',"
            "'FL-INV-9001','{}',?,'','','',NULL,?)",
            ('{"product": "Blue Dream 3.5g", "quantity": "40", "unit": "g", "room": "INV1",'
             ' "status": "on_hold"}', NOW.isoformat()))
        self.ws.conn.commit()
        self.ws.resolve_finding("drf-1", action="record_state", actor="Maria Lopez", note="their count")
        rows = self.ws.conn.execute("SELECT id, on_hold, held_at FROM lots").fetchall()
        self.assertEqual(len(rows), 1, "adopting the state's row must create the lot")
        self.assertEqual(rows[0]["on_hold"], 1)
        self.assertTrue(rows[0]["held_at"],
                        "a hold this record creates must carry the moment it learned of it")

    def test_an_older_record_gains_the_column_and_keeps_its_hold_undated(self):
        # build a record the way the previous build did, then open it
        old = Path(self.tmp.name) / "old.sqlite3"
        raw = sqlite3.connect(old)
        raw.executescript(
            "CREATE TABLE facilities (id TEXT PRIMARY KEY, name TEXT, license_number TEXT,"
            " street TEXT, city TEXT, state TEXT, zip TEXT, created_at TEXT);"
            "CREATE TABLE rooms (id TEXT PRIMARY KEY, facility_id TEXT, kind TEXT, name TEXT,"
            " number TEXT, is_quarantine INTEGER, created_at TEXT);"
            "CREATE TABLE lots (id TEXT PRIMARY KEY, product_id TEXT, room_id TEXT, quantity TEXT,"
            " unit TEXT, on_hold INTEGER, created_at TEXT);"
            "INSERT INTO lots VALUES ('lot-old','p1','inv1','40','g',1,'2026-11-01T00:00:00+00:00');")
        raw.commit()
        raw.close()
        ws = Workspace(old)
        try:
            columns = {r[1] for r in ws.conn.execute("PRAGMA table_info(lots)")}
            self.assertIn("held_at", columns)
            held = ws.conn.execute("SELECT held_at FROM lots WHERE id='lot-old'").fetchone()[0]
            self.assertEqual(held, "", "an unknown date must stay unknown, not become the created_at")
        finally:
            ws.close()


class TestTheScreenSaysSoToo(base):
    def test_today_ages_a_held_lot_instead_of_dashing_it(self):
        from test_lan_gate import Server

        self.lot(on_hold=False)
        real = datetime.now(timezone.utc)
        self.ws.amend_lot("lot-1", new_on_hold=True, cause="contamination", reason="mold found",
                          when=real - timedelta(days=6))
        server = Server(self.db, lan=False)
        server.wait()
        try:
            status, body, _ = server.get("/")
            self.assertEqual(status, 200)
            self.assertIn("6 d old", body)
            self.assertNotIn("age unknown", body)
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
