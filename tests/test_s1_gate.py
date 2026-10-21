"""S1 gate: an operator's export becomes a working record, with no manual SQL.

This test runs the real command line in a subprocess, against a real SQLite file, and
checks the artifact an operator would actually send: the DH5058 inventory list.
"""

import csv
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "operator_export.csv"
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "coontie.cli", *args],
        cwd=cwd,
        env=ENV,
        capture_output=True,
        text=True,
    )


class TestS1Gate(unittest.TestCase):
    def test_export_becomes_record_and_form(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)

            init = run(
                work,
                "init",
                "--db", "ws.sqlite3",
                "--name", "Nature's Grace FL, LLC",
                "--license", "MMTC-2026-0030",
                "--room", "inventory:INV1:01",
                "--room", "inventory:INV2:02",
                "--room", "grow:G1:03",
            )
            self.assertEqual(init.returncode, 0, init.stderr)

            imp = run(work, "--db", "ws.sqlite3", "import", "--csv", str(FIXTURE))
            self.assertIn(imp.returncode, (0, 2), imp.stderr)
            self.assertIn("imported 7/9 rows", imp.stdout)
            self.assertIn("5 new products", imp.stdout)
            self.assertIn("7 lots", imp.stdout)
            self.assertIn("failed rows were skipped", imp.stdout)

            inv = run(work, "--db", "ws.sqlite3", "inventory")
            self.assertEqual(inv.returncode, 0, inv.stderr)
            self.assertIn("7 lot(s)", inv.stdout)

            exp = run(work, "--db", "ws.sqlite3", "export", "dh5058", "--out", "dh5058.csv")
            self.assertEqual(exp.returncode, 0, exp.stderr)
            self.assertIn("5 row(s), 15 columns", exp.stdout)

            text = (work / "dh5058.csv").read_text(encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO(text)))
            self.assertEqual(len(rows), 5)

            from coontie.forms import COLUMNS

            self.assertEqual(list(rows[0].keys()), list(COLUMNS))
            for row in rows:
                self.assertEqual(row["MMTC Name"], "Nature's Grace FL, LLC")
                self.assertTrue(row["Unique Product ID"])
                self.assertIn(row["Route of Administration"], {"Edible", "Inhalation", "Oral", "Sublingual", "Suppository", "Topical", "Smoking"})
                self.assertIn(row["Marijuana Delivery Device"], {"Yes", "No"})

            types = {row["Product Type"] for row in rows}
            self.assertIn("Whole Flower", types)
            self.assertIn("Gelatin", types)

            ver = run(work, "--db", "ws.sqlite3", "verify")
            self.assertEqual(ver.returncode, 0, ver.stderr)
            self.assertIn("OK", ver.stdout)

    def test_workspace_is_a_plain_sqlite_file(self):
        """The operator owns the file: any SQLite reader can open it, no service in the way."""
        import sqlite3

        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            run(work, "init", "--db", "ws.sqlite3", "--name", "X", "--license", "L", "--room", "inventory:INV1:01")
            conn = sqlite3.connect(work / "ws.sqlite3")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"facilities", "rooms", "products", "lots", "events"} <= tables)
            conn.close()

    def test_second_import_does_not_duplicate_the_catalogue(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            run(work, "init", "--db", "ws.sqlite3", "--name", "X", "--license", "L", "--room", "inventory:INV1:01")
            run(work, "--db", "ws.sqlite3", "import", "--csv", str(FIXTURE))
            second = run(work, "--db", "ws.sqlite3", "import", "--csv", str(FIXTURE))
            self.assertIn("0 new products", second.stdout)
            self.assertIn("7 reused", second.stdout)
            exp = run(work, "--db", "ws.sqlite3", "export", "dh5058", "--out", "dh5058.csv")
            self.assertIn("5 row(s)", exp.stdout)

    def test_dry_run_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            run(work, "init", "--db", "ws.sqlite3", "--name", "X", "--license", "L", "--room", "inventory:INV1:01")
            dry = run(work, "--db", "ws.sqlite3", "import", "--csv", str(FIXTURE), "--dry-run")
            self.assertIn("would import 7/9 rows", dry.stdout)
            inv = run(work, "--db", "ws.sqlite3", "inventory")
            self.assertIn("no inventory yet", inv.stdout)


if __name__ == "__main__":
    unittest.main()
