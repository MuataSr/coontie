"""Drift gate: the department's export against the record, on the appliance screens.

The point of this screen is that a difference is a decision, not a sync. So the gate seeds a
department export with five deliberate differences, then resolves each one the way an operator
would: accept the state, recount, keep ours, record what the department has, re-send what it lost.
Then it proves every decision is on the ledger.
"""

import http.cookiejar
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
sys.path.insert(0, str(ROOT / "src"))

from coontie.importer import import_csv  # noqa: E402
from coontie.workspace import Facility, Lot, Room, Workspace  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "operator_export.csv"
HEADER = "Inventory ID,Product Name,Quantity,UOM,Status,Room,Notes"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(db: Path) -> None:
    ws = Workspace(db)
    ws.add_facility(Facility(id="fac-1", name="Nature's Grace FL, LLC",
                             license_number="MMTC-2026-0030"))
    ws.add_room(Room(id="inv1", facility_id="fac-1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="fac-1", kind="inventory", name="INV2", number="02"))
    import_csv(ws, FIXTURE, facility_id="fac-1")
    first = next(p for p in ws.products() if p.product_type == "Whole Flower")
    ws.add_lot(Lot(id="lot-unlinked", product_id=first.id, room_id="inv1",
                   quantity=Decimal("50"), unit="g"))
    rows = [r["id"] for r in ws.conn.execute(
        "SELECT id FROM lots WHERE id != 'lot-unlinked' ORDER BY rowid")]
    for index, lot_id in enumerate(rows, start=1):
        ws.link_lot(lot_id, f"FL-INV-{index:03d}")
    ws.close()


def state_csv(ws: Workspace) -> str:
    """Every linked lot, with four deliberate differences and one the department has and we do not."""
    lots = list(ws.conn.execute(
        "SELECT l.*, p.name AS product, r.name AS room FROM lots l"
        " JOIN products p ON p.id=l.product_id JOIN rooms r ON r.id=l.room_id"
        " WHERE l.sts_inventory_id IS NOT NULL ORDER BY l.rowid"))
    lines = [HEADER]
    for r in lots:
        key = r["sts_inventory_id"]
        qty, unit, status = r["quantity"], r["unit"], "Active"
        if key == "FL-INV-001":
            qty = "118"                       # quantity differs
        elif key == "FL-INV-002":
            qty, unit = "2.117", "oz"         # the same amount in ounces: must not be flagged
        elif key == "FL-INV-003":
            status = "ON HOLD"                # status differs
        lines.append(f"{key},{r['product']},{qty},{unit},{status},{r['room']},")
    lines.append("FL-INV-900,Nightshade Gummies 10pk,40,units,Active,INV1,")   # missing locally
    return "\n".join(lines) + "\n"


class Appliance:
    def __init__(self, db: Path):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "coontie.cli", "--db", str(db), "serve", "--port", str(self.port)],
            env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{self.base}/health", timeout=1) as r:
                    if r.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.2)
        # the handle exists from Popen onward, so a start that never answers must not orphan the child
        self.stop()
        raise RuntimeError("server did not start")

    def token(self) -> str:
        for cookie in self.jar:
            if cookie.name == "coontie_session":
                return cookie.value
        return ""

    def get(self, path: str) -> tuple[int, str]:
        try:
            with self.opener.open(f"{self.base}{path}", timeout=15) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def form(self, path: str, action: str, **fields) -> tuple[int, str]:
        payload = {"token": self.token(), "action": action}
        payload.update({f"{action}__{k}": v for k, v in fields.items()})
        try:
            with self.opener.open(
                    urllib.request.Request(f"{self.base}{path}",
                                           data=urllib.parse.urlencode(payload).encode()),
                    timeout=25) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def stop(self) -> None:
        # idempotent: addCleanup and tearDown may both reach here for one server
        if self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def text_of(html: str) -> str:
    body = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


class TestDrift(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        seed(self.db)
        self.app = Appliance(self.db)
        # registered here, not only in tearDown: unittest skips tearDown when setUp raises,
        # which is how 25 orphaned servers accumulated before this line existed
        self.addCleanup(self.app.stop)
        self.app.get("/drift")

    def tearDown(self):
        self.app.stop()
        self.tmp.cleanup()

    def test_1_an_unlinked_lot_is_counted_out_loud(self):
        _status, html = self.app.get("/drift")
        text = text_of(html)
        self.assertIn("Lots with no department id (1)", text)
        self.assertIn("lot-unlinked", html)

    def test_2_reading_an_export_lists_the_differences_and_not_the_false_ones(self):
        ws = Workspace(self.db)
        csv = state_csv(ws)
        ws.close()
        status, html = self.app.form("/drift", "pull", text=csv)
        self.assertEqual(status, 200)
        text = text_of(html)
        self.assertIn("Read 8 rows", text)
        self.assertIn("Open differences", text)
        # the ounce row is the same amount and must not be flagged
        self.assertNotIn("FL-INV-002", text)
        self.assertIn("FL-INV-001", text)      # quantity differs
        self.assertIn("FL-INV-003", text)      # status differs
        self.assertIn("FL-INV-900", text)      # the department has it, we do not

    def test_3_every_decision_is_a_button_and_each_one_is_recorded(self):
        ws = Workspace(self.db)
        csv = state_csv(ws)
        ws.close()
        self.app.form("/drift", "pull", text=csv)

        ws = Workspace(self.db)
        findings = ws.drift_findings(open_only=True)
        ws.close()
        by_kind: dict[str, list] = {}
        for f in findings:
            by_kind.setdefault(f["kind"], []).append(f)
        self.assertIn("quantity_mismatch", by_kind)
        self.assertIn("status_mismatch", by_kind)
        self.assertIn("missing_locally", by_kind)

        # accept the state on the quantity difference
        qty = by_kind["quantity_mismatch"][0]
        status, html = self.app.form("/drift", "resolve", finding=qty["id"], act="accept_state")
        self.assertEqual(status, 200)
        self.assertIn("settled: accept state", text_of(html))

        # keep ours on the status difference
        status = by_kind["status_mismatch"][0]
        _s, html = self.app.form("/drift", "resolve", finding=status["id"], act="keep_local")
        self.assertIn("settled: keep local", text_of(html))

        # record what the department has, for the lot we do not hold
        missing = by_kind["missing_locally"][0]
        _s, html = self.app.form("/drift", "resolve", finding=missing["id"], act="record_state")
        self.assertIn("settled: record state", text_of(html))

        _s, page = self.app.get("/drift")
        self.assertIn("Settled", text_of(page))
        self.assertIn("0 open", page)

    def test_4_a_recount_needs_a_number_and_refuses_without_one(self):
        ws = Workspace(self.db)
        csv = state_csv(ws)
        ws.close()
        self.app.form("/drift", "pull", text=csv)
        ws = Workspace(self.db)
        qty = [f for f in ws.drift_findings(open_only=True) if f["kind"] == "quantity_mismatch"][0]
        ws.close()
        status, html = self.app.form("/drift", "resolve", finding=qty["id"], act="recount")
        self.assertEqual(status, 200)
        self.assertIn("counted quantity", text_of(html))
        _s, html = self.app.form("/drift", "resolve", finding=qty["id"], act="recount",
                                 quantity="118")
        self.assertIn("settled: recount", text_of(html))

    def test_5_a_lot_can_be_linked_to_its_department_id(self):
        status, html = self.app.form("/drift", "link", lot="lot-unlinked", sts="FL-INV-777")
        self.assertIn("linked to FL-INV-777", text_of(html))
        ws = Workspace(self.db)
        try:
            row = ws.conn.execute("SELECT sts_inventory_id FROM lots WHERE id = 'lot-unlinked'").fetchone()
        finally:
            ws.close()
        self.assertEqual(row["sts_inventory_id"], "FL-INV-777")

    def test_6_resolving_twice_is_refused_and_the_second_attempt_writes_nothing(self):
        ws = Workspace(self.db)
        csv = state_csv(ws)
        ws.close()
        self.app.form("/drift", "pull", text=csv)
        ws = Workspace(self.db)
        qty = [f for f in ws.drift_findings(open_only=True) if f["kind"] == "quantity_mismatch"][0]
        ws.close()
        self.app.form("/drift", "resolve", finding=qty["id"], act="accept_state")
        status, html = self.app.form("/drift", "resolve", finding=qty["id"], act="accept_state")
        self.assertEqual(status, 200)
        self.assertIn("already resolved", text_of(html))

    def test_7_the_decisions_are_on_the_ledger_and_the_chain_verifies(self):
        ws = Workspace(self.db)
        csv = state_csv(ws)
        ws.close()
        self.app.form("/drift", "pull", text=csv)
        ws = Workspace(self.db)
        qty = [f for f in ws.drift_findings(open_only=True) if f["kind"] == "quantity_mismatch"][0]
        ws.close()
        self.app.form("/drift", "resolve", finding=qty["id"], act="accept_state")
        ws = Workspace(self.db)
        try:
            ok, message = ws.verify()
            self.assertTrue(ok, message)
            keys = [e.event_key for e in ws.ledger.entries()]
        finally:
            ws.close()
        self.assertIn("drift_resolution", keys)
        self.assertEqual(keys.count("drift_resolution"), 1)

    def test_9_a_finding_names_both_numbers_rather_than_only_that_they_differ(self):
        from coontie.inspect import inspect

        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                ws.pull_state(state_csv(ws), source_file="state.csv")
                ws.compare_drift()
                lines = [f.summary for f in inspect(ws) if f.code == "drift_open"]
            finally:
                ws.close()
            self.assertTrue(lines, "no drift findings reached the inspector")
            joined = " ".join(lines)
            self.assertRegex(joined, r"quantity ours \d+, theirs \d+")
            self.assertRegex(
                joined,
                r"(the export has .* and no such lot is held here"
                r"|this record holds .* and the export has no such lot)",
            )
            self.assertNotIn("ours not held", joined)
            self.assertNotRegex(joined, r"\d\.0\b")     # 35.0 is a parser artefact, not a quantity

    def test_8_the_screen_ships_no_javascript_and_needs_the_token(self):
        _status, html = self.app.get("/drift")
        self.assertNotIn("<script", html.lower())
        self.assertIn("name='token'", html.replace('"', "'"))
        payload = {"action": "pull", "pull__text": HEADER}
        req = urllib.request.Request(f"{self.app.base}/drift",
                                     data=urllib.parse.urlencode(payload).encode())
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
