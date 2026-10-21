"""S3 gate: a two-hour disconnection drafts its notice, and restoration yields the CSV.

Nothing here types a notice. Between the disconnection and the restoration the only
command that runs is `watch`, which is the unattended tick.
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
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "coontie.cli", *args], cwd=cwd, env=ENV, capture_output=True, text=True
    )


def setup(work: Path) -> None:
    init = run(work, "init", "--db", "ws.sqlite3", "--name", "Nature's Grace FL, LLC",
               "--license", "MMTC-2026-0030", "--room", "inventory:INV1:01")
    assert init.returncode == 0, init.stderr


class TestS3Gate(unittest.TestCase):
    def test_two_hour_disconnection_is_reported_unattended(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)

            # A dispensation before the outage must not appear in the outage CSV.
            before = run(work, "--db", "ws.sqlite3", "dispense", "--patient", "MMUR-BEFORE",
                         "--inventory", "FL-INV-000", "--weight", "1", "--at", "2026-10-21T07:00:00Z", "--mmur-verified")
            self.assertEqual(before.returncode, 0, before.stderr)

            start = run(work, "--db", "ws.sqlite3", "outage", "--start", "--at", "2026-10-21T08:00:00Z")
            self.assertEqual(start.returncode, 0, start.stderr)

            # Under two hours: nothing is due.
            under = run(work, "--db", "ws.sqlite3", "watch", "--at", "2026-10-21T09:59:00Z")
            self.assertIn("nothing due", under.stdout)

            # Dispensing during the outage without MMUR verification is refused.
            refused = run(work, "--db", "ws.sqlite3", "dispense", "--patient", "MMUR-1",
                          "--inventory", "FL-INV-001", "--weight", "3.5", "--at", "2026-10-21T09:00:00Z")
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("64-4.222(2)(a)", refused.stderr)

            verified = run(work, "--db", "ws.sqlite3", "dispense", "--patient", "MMUR-1",
                           "--inventory", "FL-INV-001", "--weight", "3.5", "--at", "2026-10-21T09:00:00Z", "--mmur-verified")
            self.assertEqual(verified.returncode, 0, verified.stderr)

            # Past two hours: the notice drafts itself. No other command has run.
            tick = run(work, "--db", "ws.sqlite3", "watch", "--at", "2026-10-21T10:01:00Z")
            self.assertEqual(tick.returncode, 0, tick.stderr)
            self.assertIn("drafted disconnection notice", tick.stdout)

            notices = list((work / "reports").glob("*notice.txt"))
            self.assertEqual(len(notices), 1)
            notice = notices[0].read_text(encoding="utf-8")
            self.assertIn("ommu_seedtosale@flhealth.gov", notice)
            self.assertIn("64-4.222(2)", notice)
            self.assertIn("Dispensations recorded during the disconnection so far: 1", notice)
            self.assertIn("2h01m", notice)

            # Still unsent after the 3-hour mark: the clock records a breach rather than forgetting.
            breach = run(work, "--db", "ws.sqlite3", "watch", "--at", "2026-10-21T12:00:00Z")
            self.assertIn("BREACH", breach.stdout)
            self.assertIn("notice", breach.stdout.lower())

            # Restoration: the restoration notice and the CSV appear immediately.
            restore = run(work, "--db", "ws.sqlite3", "outage", "--restore", "--at", "2026-10-21T13:00:00Z")
            self.assertEqual(restore.returncode, 0, restore.stderr)
            self.assertIn("1 dispensations", restore.stdout)

            csv_files = list((work / "reports").glob("*dispensations.csv"))
            self.assertEqual(len(csv_files), 1)
            rows = list(csv.DictReader(io.StringIO(csv_files[0].read_text(encoding="utf-8"))))
            self.assertEqual(len(rows), 1, rows)                      # only the in-outage dispensation
            self.assertEqual(rows[0]["Patient ID Number"], "MMUR-1")
            self.assertEqual(rows[0]["Department Seed-to-Sale Inventory Identification Number"], "FL-INV-001")
            self.assertEqual(rows[0]["Weight Dispensed"], "3.5")
            self.assertEqual(rows[0]["Dispensing Facility Location"], "Nature's Grace FL, LLC")
            self.assertTrue(rows[0]["Date and Time of Dispensation"].startswith("2026-10-21T09:00"))

            restorations = list((work / "reports").glob("*restoration.txt"))
            self.assertEqual(len(restorations), 1)
            self.assertIn("5h00m", restorations[0].read_text(encoding="utf-8"))

            # The 24-hour report deadline is enforced by the clock too.
            late = run(work, "--db", "ws.sqlite3", "watch", "--at", "2026-10-22T13:01:00Z")
            self.assertIn("BREACH", late.stdout)
            self.assertIn("CSV", late.stdout)

            verify = run(work, "--db", "ws.sqlite3", "verify")
            self.assertIn("OK", verify.stdout)

    def test_short_disconnection_needs_no_notice_but_still_gets_the_csv(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)
            run(work, "--db", "ws.sqlite3", "outage", "--start", "--at", "2026-10-21T08:00:00Z")
            run(work, "--db", "ws.sqlite3", "watch", "--at", "2026-10-21T09:00:00Z")
            restore = run(work, "--db", "ws.sqlite3", "outage", "--restore", "--at", "2026-10-21T09:30:00Z")
            self.assertEqual(restore.returncode, 0, restore.stderr)
            self.assertEqual(list((work / "reports").glob("*notice.txt")), [])
            self.assertEqual(len(list((work / "reports").glob("*dispensations.csv"))), 1)

    def test_sending_is_recorded_and_stops_the_breach(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)
            run(work, "--db", "ws.sqlite3", "outage", "--start", "--at", "2026-10-21T08:00:00Z")
            run(work, "--db", "ws.sqlite3", "watch", "--at", "2026-10-21T10:05:00Z")
            send = run(work, "--db", "ws.sqlite3", "outage", "--send", "notice", "--at", "2026-10-21T10:30:00Z")
            self.assertEqual(send.returncode, 0, send.stderr)
            self.assertIn("ommu_seedtosale@flhealth.gov", send.stdout)
            after = run(work, "--db", "ws.sqlite3", "watch", "--at", "2026-10-21T12:00:00Z")
            self.assertNotIn("BREACH", after.stdout)

            shown = run(work, "--db", "ws.sqlite3", "outage", "--show", "--at", "2026-10-21T12:00:00Z")
            self.assertIn("sent_on_time", shown.stdout)


if __name__ == "__main__":
    unittest.main()
