"""The soak is a test, so the soak needs a test.

Two claims are worth pinning: a short month passes with every invariant checked, and the seed
reproduces the month it describes. Ids are uuids and `recorded_at` is wall clock, so byte-identical
runs are impossible and are not claimed; what is claimed is the schedule and the values the seed chose.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "soak.py"
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def soak(db: Path, *, days: int = 3, seed: int = 11, keep: bool = False, report: Path | None = None):
    argv = [sys.executable, str(SCRIPT), "--db", str(db), "--days", str(days), "--seed", str(seed),
            "--quiet"]
    if keep:
        argv.append("--keep")
    if report:
        argv += ["--report", str(report)]
    return subprocess.run(argv, capture_output=True, text=True, env=ENV)


class TestSoak(unittest.TestCase):
    def test_a_short_month_passes_and_reports_what_it_did(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            report = Path(d) / "report.json"
            proc = soak(db, days=4, keep=True, report=report)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("soak passed", proc.stdout)
            data = json.loads(report.read_text())
            self.assertGreater(data["events"], 40)
            self.assertEqual(data["days"], 4)
            self.assertIn("shape", data["fingerprint"])
            self.assertTrue(data["chain_head"])

    def test_the_record_it_leaves_behind_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            proc = soak(db, days=3, keep=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            check = subprocess.run([sys.executable, "-m", "coontie.cli", "--db", str(db), "verify"],
                                   capture_output=True, text=True, env=ENV)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("ok", check.stdout.lower())

    def test_the_same_seed_reproduces_the_schedule_and_the_values_it_chose(self):
        with tempfile.TemporaryDirectory() as d:
            first = soak(Path(d) / "one" / "ws.sqlite3", days=4, seed=21, keep=True, report=Path(d) / "a.json")
            second = soak(Path(d) / "two" / "ws.sqlite3", days=4, seed=21, keep=True, report=Path(d) / "b.json")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            a = json.loads((Path(d) / "a.json").read_text())["fingerprint"]
            b = json.loads((Path(d) / "b.json").read_text())["fingerprint"]
            self.assertEqual(a["events"], b["events"])
            self.assertEqual(a["shape"], b["shape"], "the same seed ran a different month")
            self.assertEqual(a["seeded"], b["seeded"], "the same seed chose different values")

    def test_a_different_seed_changes_the_month(self):
        with tempfile.TemporaryDirectory() as d:
            one = soak(Path(d) / "one" / "ws.sqlite3", days=4, seed=21, keep=True,
                       report=Path(d) / "a.json")
            other = soak(Path(d) / "two" / "ws.sqlite3", days=4, seed=22, keep=True,
                         report=Path(d) / "b.json")
            self.assertEqual(one.returncode, 0, one.stderr)
            self.assertEqual(other.returncode, 0, other.stderr)
            a = json.loads((Path(d) / "a.json").read_text())["fingerprint"]
            b = json.loads((Path(d) / "b.json").read_text())["fingerprint"]
            self.assertNotEqual(a["seeded"], b["seeded"])

    def test_a_soak_will_not_run_on_a_record_that_exists(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            db.write_bytes(b"SQLite format 3\x00 not really a record")
            proc = soak(db, days=1)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("already exists", proc.stderr)
            self.assertEqual(db.read_bytes(), b"SQLite format 3\x00 not really a record",
                             "the soak touched a file it refused to use")

    def test_without_keep_the_synthetic_record_is_removed(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            proc = soak(db, days=2, keep=False)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("record removed", proc.stdout)
            self.assertFalse(db.exists())


if __name__ == "__main__":
    unittest.main()
