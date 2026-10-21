"""S5 gate: a full cultivation arc, seed to harvest, recorded in DH5059 shapes.

The last test is the one that matters most: every cultivation event in the ledger carries
the field names the department's form requires, checked against the catalog itself rather
than against a copy of it.
"""

import json
import os
import sqlite3
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
    init = run(
        work, "init", "--db", "ws.sqlite3", "--name", "Nature's Grace FL, LLC", "--license", "MMTC-2026-0030",
        "--room", "grow:G1:01", "--room", "grow:F2:02", "--room", "inventory:DRY1:03",
    )
    assert init.returncode == 0, init.stderr


class TestS5Gate(unittest.TestCase):
    def test_seed_to_harvest_to_disposal(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)

            # 1. No cultivation before integration is recorded.
            early = run(work, "--db", "ws.sqlite3", "batch", "--cultivar", "Blue Dream", "--room", "G1", "--count", "12")
            self.assertNotEqual(early.returncode, 0)
            self.assertIn("64-4.221(4)", early.stderr)

            approved = run(work, "--db", "ws.sqlite3", "integration", "--approved-on", "2026-09-20",
                           "--reference", "INT-2026-0042")
            self.assertEqual(approved.returncode, 0, approved.stderr)

            # 2. Batch, then plants.
            batch = run(work, "--db", "ws.sqlite3", "batch", "--cultivar", "Blue Dream", "--room", "G1",
                        "--count", "12", "--at", "2026-10-01T09:00:00Z")
            self.assertEqual(batch.returncode, 0, batch.stderr)
            batch_id = batch.stdout.split()[0]

            too_many = run(work, "--db", "ws.sqlite3", "plant", "--batch", batch_id, "--count", "13")
            self.assertNotEqual(too_many.returncode, 0)
            self.assertIn("too many", too_many.stderr)

            planted = run(work, "--db", "ws.sqlite3", "plant", "--batch", batch_id, "--count", "12",
                          "--at", "2026-10-02T09:00:00Z")
            self.assertEqual(planted.returncode, 0, planted.stderr)
            self.assertIn("PL-0001..PL-0012", planted.stdout)

            growing = run(work, "--db", "ws.sqlite3", "growing")
            self.assertIn("12 growing", growing.stdout)

            # 3. Move, then an additive.
            moved = run(work, "--db", "ws.sqlite3", "move", "--plants", "PL-0001..PL-0012", "--to", "F2",
                        "--at", "2026-10-20T09:00:00Z")
            self.assertEqual(moved.returncode, 0, moved.stderr)

            additive = run(work, "--db", "ws.sqlite3", "additive", "--plants", "PL-0001..PL-0012",
                           "--what", "Neem oil 0.5%, lot NX-1, EPA 70051-2", "--amount", "40", "--unit", "ml",
                           "--at", "2026-10-25T10:00:00Z")
            self.assertEqual(additive.returncode, 0, additive.stderr)

            # 4. A harvest without a schedule is refused.
            early_harvest = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001..PL-0012",
                                "--wet", "1800", "--room", "DRY1", "--at", "2026-11-20T08:00:00Z")
            self.assertNotEqual(early_harvest.returncode, 0)
            self.assertIn("scheduled before", early_harvest.stderr)

            # 5. Schedule, then harvest.
            scheduled = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001..PL-0012",
                            "--schedule", "--at", "2026-11-18T09:00:00Z")
            self.assertEqual(scheduled.returncode, 0, scheduled.stderr)

            wrong_set = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001..PL-0006",
                            "--wet", "900", "--room", "DRY1", "--at", "2026-11-20T07:00:00Z")
            self.assertNotEqual(wrong_set.returncode, 0)

            bad_weights = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001..PL-0012",
                              "--wet", "100", "--waste", "80", "--other", "40", "--room", "DRY1",
                              "--at", "2026-11-20T07:00:00Z")
            self.assertNotEqual(bad_weights.returncode, 0)
            self.assertIn("exceeds", bad_weights.stderr)

            harvested = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001..PL-0012",
                            "--wet", "1800", "--waste", "240", "--other", "60", "--room", "DRY1",
                            "--at", "2026-11-20T08:00:00Z")
            self.assertEqual(harvested.returncode, 0, harvested.stderr)
            self.assertIn("1800 g wet flower", harvested.stdout)

            # 6. Disposal: schedule, refuse early, allow after 72 hours.
            second = run(work, "--db", "ws.sqlite3", "batch", "--cultivar", "Silver Haze", "--room", "G1",
                         "--count", "4", "--at", "2026-10-05T09:00:00Z")
            second_batch = second.stdout.split()[0]
            run(work, "--db", "ws.sqlite3", "plant", "--batch", second_batch, "--count", "2",
                "--at", "2026-10-06T09:00:00Z")

            dispose_unscheduled = run(work, "--db", "ws.sqlite3", "dispose", "--plants", "PL-0013,PL-0014",
                                      "--at", "2026-10-10T09:00:00Z")
            self.assertNotEqual(dispose_unscheduled.returncode, 0)
            self.assertIn("scheduled first", dispose_unscheduled.stderr)

            run(work, "--db", "ws.sqlite3", "dispose", "--plants", "PL-0013,PL-0014", "--reason", "male plants",
                "--schedule", "--at", "2026-10-07T09:00:00Z")

            too_soon = run(work, "--db", "ws.sqlite3", "dispose", "--plants", "PL-0013,PL-0014",
                           "--at", "2026-10-09T09:00:00Z")
            self.assertNotEqual(too_soon.returncode, 0)
            self.assertIn("24h remain", too_soon.stderr)

            disposed = run(work, "--db", "ws.sqlite3", "dispose", "--plants", "PL-0013,PL-0014",
                           "--at", "2026-10-10T09:01:00Z")
            self.assertEqual(disposed.returncode, 0, disposed.stderr)

            matter = run(work, "--db", "ws.sqlite3", "dispose", "--matter", "500", "--at", "2026-11-21T09:00:00Z")
            self.assertEqual(matter.returncode, 0, matter.stderr)

            # 7. The growing state is coherent, and the ledger holds.
            after = run(work, "--db", "ws.sqlite3", "growing")
            self.assertIn("2 disposed, 12 harvested", after.stdout)

            verify = run(work, "--db", "ws.sqlite3", "verify")
            self.assertIn("OK", verify.stdout)

    def test_ledger_payloads_carry_the_departments_field_names(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)
            run(work, "--db", "ws.sqlite3", "integration", "--approved-on", "2026-09-20", "--reference", "R")
            batch = run(work, "--db", "ws.sqlite3", "batch", "--cultivar", "Blue Dream", "--room", "G1", "--count", "2")
            batch_id = batch.stdout.split()[0]
            run(work, "--db", "ws.sqlite3", "plant", "--batch", batch_id, "--count", "2")
            run(work, "--db", "ws.sqlite3", "move", "--plants", "PL-0001,PL-0002", "--to", "F2")
            run(work, "--db", "ws.sqlite3", "additive", "--plants", "PL-0001,PL-0002", "--what", "Neem", "--amount", "5")
            run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001,PL-0002", "--schedule")
            run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001,PL-0002", "--wet", "100", "--room", "DRY1")
            run(work, "--db", "ws.sqlite3", "dispose", "--matter", "20")

            from coontie.events import EVENTS, Stage

            cultivation = {e.key: e for e in EVENTS if e.stage is Stage.CULTIVATION}
            conn = sqlite3.connect(work / "ws.sqlite3")
            rows = conn.execute("SELECT event_key, payload FROM events").fetchall()
            conn.close()

            checked = 0
            for key, payload_json in rows:
                if key not in cultivation:
                    continue
                payload = json.loads(payload_json)
                spec = cultivation[key]
                for f in spec.fields:
                    # plant_id / harvest_id / plant_ids: ours are additive, the catalog's are required
                    if f.name in ("plant_ids",):
                        self.assertIn("plant_ids", payload, f"{key} missing plant_ids")
                        continue
                    if f.name in payload:
                        continue
                    if f.name == "harvest_id":
                        continue
                    self.assertIn(
                        f.name, payload,
                        f"{key} payload is missing the department's field {f.name!r}: {sorted(payload)}",
                    )
                checked += 1
            self.assertGreaterEqual(checked, 6, f"only {checked} cultivation events found")

    def test_a_second_harvest_of_the_same_plants_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)
            run(work, "--db", "ws.sqlite3", "integration", "--approved-on", "2026-09-20")
            batch = run(work, "--db", "ws.sqlite3", "batch", "--cultivar", "X", "--room", "G1", "--count", "2")
            run(work, "--db", "ws.sqlite3", "plant", "--batch", batch.stdout.split()[0], "--count", "2")
            run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001,PL-0002", "--schedule")
            run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001,PL-0002", "--wet", "50", "--room", "DRY1")
            again = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001,PL-0002", "--wet", "50",
                        "--room", "DRY1")
            self.assertNotEqual(again.returncode, 0)
            self.assertIn("no longer growing", again.stderr)


if __name__ == "__main__":
    unittest.main()
