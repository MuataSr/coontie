"""S4 gate: ten seeded differences, each detected, classified, and resolved on the screen.

The screen is a real HTTP page served from the workspace, and the resolutions in this test
are real form posts, not function calls.
"""

import sqlite3
import threading
import unittest
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
import tempfile

from coontie.driftview import make_server
from coontie.importer import import_csv
from coontie.workspace import Facility, Lot, Room, Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "operator_export.csv"

STATE_HEADER = "Inventory ID,Product Name,Quantity,UOM,Status,Room,Notes\n"


def seed(db: Path) -> Workspace:
    ws = Workspace(db)
    ws.add_facility(Facility(id="fac-1", name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030"))
    ws.add_room(Room(id="inv1", facility_id="fac-1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="fac-1", kind="inventory", name="INV2", number="02"))
    import_csv(ws, FIXTURE, facility_id="fac-1")
    first_product = next(p for p in ws.products() if p.product_type == "Whole Flower")
    ws.add_lot(Lot(id="lot-extra", product_id=first_product.id, room_id="inv1", quantity=Decimal("50"), unit="g"))
    rows = list(ws.conn.execute("SELECT id FROM lots ORDER BY rowid"))
    for i, row in enumerate(rows, start=1):
        ws.link_lot(row["id"], f"FL-INV-{i:03d}")
    return ws


def build_state_csv(ws: Workspace) -> str:
    """Eight of our records with five deliberate changes, plus three the state has and we do not."""
    lots = list(
        ws.conn.execute(
            "SELECT l.*, p.name AS product, r.name AS room FROM lots l"
            " JOIN products p ON p.id=l.product_id JOIN rooms r ON r.id=l.room_id"
            " WHERE l.sts_inventory_id IS NOT NULL ORDER BY l.rowid"
        )
    )
    by_id = {r["sts_inventory_id"]: r for r in lots}

    lines = [STATE_HEADER.strip()]
    for key in ("FL-INV-001", "FL-INV-002", "FL-INV-003", "FL-INV-004", "FL-INV-007", "FL-INV-008"):
        r = by_id[key]
        qty, unit, status = r["quantity"], r["unit"], "Active"
        if key == "FL-INV-001":
            qty = "118"                      # quantity differs
        elif key == "FL-INV-002":
            qty, unit = "2.117", "oz"        # same amount in ounces: must not be flagged
        elif key == "FL-INV-003":
            status = "ON HOLD"               # status differs
        elif key == "FL-INV-004":
            status = "Quarantine"            # status differs
        elif key == "FL-INV-007":
            qty = str(Decimal(r["quantity"]) + 3)   # quantity differs
        elif key == "FL-INV-008":
            qty = "45"                       # quantity differs
        lines.append(f"{key},{r['product']},{qty},{unit},{status},{r['room']},")

    lines.append("FL-INV-900,Nightshade Gummies 10pk,40,units,Active,INV1,")   # missing locally
    lines.append("FL-INV-901,Relief Salve 2oz,12,units,Active,INV1,")          # missing locally
    lines.append("FL-INV-902,Vape Cart .5g,15,units,Active,INV2,")             # missing locally
    return "\n".join(lines) + "\n"


class TestS4Gate(unittest.TestCase):
    def test_ten_differences_detected_classified_and_resolved_on_screen(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            ws = seed(db)
            state_csv = build_state_csv(ws)
            (Path(d) / "state.csv").write_text(state_csv, encoding="utf-8")

            sid, rows, rejected = ws.pull_state(state_csv, source_file="state.csv")
            self.assertEqual(rows, 9)
            self.assertEqual(rejected, 0)
            report, _ = ws.compare_drift()

            # Ten differences, in the four classes, and the ounce record is not one of them.
            self.assertEqual(len(report.items), 10, report.summary())
            kinds = report.by_kind()
            self.assertEqual(kinds["quantity_mismatch"], 3)
            self.assertEqual(kinds["status_mismatch"], 2)
            self.assertEqual(kinds["missing_at_state"], 2)
            self.assertEqual(kinds["missing_locally"], 3)
            self.assertNotIn("FL-INV-002", {i.key for i in report.items})

            ws.close()

            # The screen, served for real.
            server_ws = Workspace(db)
            server = make_server(server_ws, 0)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{port}"
            try:
                page = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
                self.assertIn("Your record vs the state", page)
                self.assertIn("10", page)
                self.assertIn("differences", page)
                self.assertIn("FL-INV-001", page)
                self.assertIn("Accept the state", page)
                self.assertIn("Record it here", page)

                findings = {f"{f['kind']}:{f['record_key']}": f["id"] for f in server_ws.drift_findings()}
                self.assertEqual(len(findings), 10)

                def post(fid, action, **extra):
                    body = urllib.parse.urlencode({"id": fid, "action": action, **extra}).encode()
                    return urllib.request.urlopen(base + "/resolve", data=body, timeout=5).read().decode("utf-8")

                post(findings["quantity_mismatch:FL-INV-001"], "accept_state")
                page = post(findings["quantity_mismatch:FL-INV-007"], "recount", quantity="201")
                post(findings["quantity_mismatch:FL-INV-008"], "accept_state")
                post(findings["status_mismatch:FL-INV-003"], "accept_state")
                post(findings["status_mismatch:FL-INV-004"], "keep_local")
                post(findings["missing_at_state:FL-INV-005"], "resend")
                post(findings["missing_at_state:FL-INV-006"], "keep_local")
                post(findings["missing_locally:FL-INV-900"], "record_state")
                post(findings["missing_locally:FL-INV-901"], "record_state")
                page = post(findings["missing_locally:FL-INV-902"], "record_state")

                self.assertIn("0", page)
                self.assertIn("No differences", page)
            finally:
                server.shutdown()
                server.server_close()
                server_ws.close()

            # Verify the writes through a fresh connection.
            final = Workspace(db)
            self.assertEqual(final.drift_findings(open_only=True), [])
            resolved = final.drift_findings(open_only=False)
            self.assertEqual(len(resolved), 10)
            self.assertEqual(
                {f["resolution"] for f in resolved},
                {"accept_state", "recount", "keep_local", "resend", "record_state"},
            )

            lot_one = final.conn.execute(
                "SELECT quantity FROM lots WHERE sts_inventory_id='FL-INV-001'"
            ).fetchone()[0]
            self.assertEqual(Decimal(lot_one), Decimal("118"))
            lot_seven = final.conn.execute(
                "SELECT quantity FROM lots WHERE sts_inventory_id='FL-INV-007'"
            ).fetchone()[0]
            self.assertEqual(Decimal(lot_seven), Decimal("201"))
            self.assertEqual(final.conn.execute("SELECT COUNT(*) FROM lots").fetchone()[0], 11)
            recovered = final.conn.execute(
                "SELECT quantity FROM lots WHERE sts_inventory_id='FL-INV-900'"
            ).fetchone()[0]
            self.assertEqual(Decimal(recovered), Decimal("40"))

            ok, summary = final.verify()
            self.assertTrue(ok, summary)
            keys = [e.event_key for e in final.ledger.entries()]
            self.assertEqual(keys.count("drift_resolution"), 10)
            self.assertIn("inventory_adjustment", keys)
            final.close()

    def test_the_page_says_so_when_no_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as d:
            ws = seed(Path(d) / "ws.sqlite3")
            server = make_server(ws, 0)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode("utf-8")
                self.assertIn("No state snapshot yet", page)
            finally:
                server.shutdown()
                server.server_close()
                ws.close()

    def test_an_inapplicable_action_is_refused_with_the_options(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            ws = seed(db)
            ws.pull_state(build_state_csv(ws), source_file="state.csv")
            ws.compare_drift()
            missing = [f for f in ws.drift_findings() if f["kind"] == "missing_locally"][0]
            with self.assertRaises(ValueError) as ctx:
                ws.resolve_finding(missing["id"], "accept_state")
            self.assertIn("record_state", str(ctx.exception))
            ws.close()


if __name__ == "__main__":
    unittest.main()
