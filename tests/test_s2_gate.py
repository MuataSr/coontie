"""S2 gate: correct without fear.

A seeded set of wrong records is amended; every non-exempt case yields a justification
draft and a deadline; the ledger shows both versions. Run through the real CLI.
"""

import csv
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "operator_export.csv"
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "coontie.cli", *args], cwd=cwd, env=ENV, capture_output=True, text=True
    )


def setup(work: Path) -> str:
    run(work, "init", "--db", "ws.sqlite3", "--name", "Nature's Grace FL, LLC", "--license", "MMTC-2026-0030",
        "--room", "inventory:INV1:01", "--room", "inventory:INV2:02")
    run(work, "--db", "ws.sqlite3", "import", "--csv", str(FIXTURE))
    conn = sqlite3.connect(work / "ws.sqlite3")
    lot_id = conn.execute(
        "SELECT l.id FROM lots l JOIN products p ON p.id = l.product_id WHERE p.name LIKE 'Blue Dream 3.5g%' LIMIT 1"
    ).fetchone()[0]
    conn.close()
    return lot_id


class TestS2Gate(unittest.TestCase):
    def test_non_exempt_amendment_produces_draft_and_deadline(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            lot = setup(work)

            amend = run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--quantity", "118",
                        "--cause", "miscount", "--reason", "Physical recount: 118g on the shelf", "--actor", "C.Hurley")
            self.assertEqual(amend.returncode, 0, amend.stderr)
            self.assertIn("120 -> 118", amend.stdout)
            self.assertIn("(-2 g)", amend.stdout)
            self.assertIn("justification drafted", amend.stdout)
            self.assertIn("deadline:", amend.stdout)

            js = run(work, "--db", "ws.sqlite3", "justifications")
            self.assertIn("draft", js.stdout)
            self.assertIn("1 justification(s)", js.stdout)

            jid = [t for t in amend.stdout.split() if t.startswith("jst-")][0]
            show = run(work, "--db", "ws.sqlite3", "justify", jid[:8], "--show")
            self.assertIn("64-4.222(12)", show.stdout)
            self.assertIn("ommu_seedtosale@flhealth.gov", show.stdout)
            self.assertIn("Unique product ID:", show.stdout)
            self.assertIn("120 g to 118 g", show.stdout)
            self.assertIn("Physical recount", show.stdout)

            sent = run(work, "--db", "ws.sqlite3", "justify", jid[:8], "--send")
            self.assertIn("marked sent", sent.stdout)
            self.assertIn("sent_on_time", sent.stdout)

            verify = run(work, "--db", "ws.sqlite3", "verify")
            self.assertIn("OK", verify.stdout)

    def test_exempt_amendment_needs_no_paperwork(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            lot = setup(work)
            amend = run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--quantity", "110",
                        "--cause", "processing", "--reason", "10g converted to extract during processing")
            self.assertEqual(amend.returncode, 0, amend.stderr)
            self.assertIn("exempt", amend.stdout)
            js = run(work, "--db", "ws.sqlite3", "justifications", "--pending")
            self.assertIn("nothing pending", js.stdout)

    def test_ledger_shows_both_versions(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            lot = setup(work)
            run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--quantity", "118", "--cause", "miscount", "--reason", "recount")
            journal = run(work, "--db", "ws.sqlite3", "journal", "--lot", lot)
            self.assertIn("inventory_lot_create", journal.stdout)   # the original
            self.assertIn("amendment", journal.stdout)               # the correction
            self.assertIn("120 -> 118", journal.stdout)

            # The original quantity is still on the ledger, not overwritten.
            conn = sqlite3.connect(work / "ws.sqlite3")
            payloads = [r[0] for r in conn.execute("SELECT payload FROM events WHERE event_key='inventory_lot_create'")]
            conn.close()
            self.assertTrue(any('"120"' in p for p in payloads), payloads)

    def test_unknown_cause_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            lot = setup(work)
            bad = run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--quantity", "1", "--cause", "wishful", "--reason", "x")
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("unknown cause", bad.stderr)

    def test_amendments_stack_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            lot = setup(work)
            run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--quantity", "118", "--cause", "miscount", "--reason", "first")
            second = run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--quantity", "117", "--cause", "spillage", "--reason", "second")
            self.assertIn("118 -> 117", second.stdout)
            conn = sqlite3.connect(work / "ws.sqlite3")
            rows = conn.execute("SELECT before_value, after_value, sequence FROM amendments ORDER BY sequence").fetchall()
            conn.close()
            self.assertEqual(rows, [("120", "118", 1), ("118", "117", 2)])

    def test_hold_amendment_surfaces_as_blocking_alert(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            lot = setup(work)
            hold = run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--hold", "--cause", "contamination", "--reason", "lab flag pending")
            self.assertEqual(hold.returncode, 0, hold.stderr)
            alerts = run(work, "--db", "ws.sqlite3", "alerts")
            self.assertIn("BLOCK", alerts.stdout)
            self.assertIn("on hold", alerts.stdout.lower())

    def test_unsent_justification_shows_as_an_alert(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            lot = setup(work)
            run(work, "--db", "ws.sqlite3", "amend", "--lot", lot, "--quantity", "118", "--cause", "miscount", "--reason", "recount")
            alerts = run(work, "--db", "ws.sqlite3", "alerts")
            self.assertIn("adjustment_unjustified", alerts.stdout)
            self.assertIn("64-4.222(12)", alerts.stdout)


if __name__ == "__main__":
    unittest.main()
