"""S7 gate: a manifest generated from the record, and a transfer that both ends accept.

The last check is the same catalog check the stage modules use: every transport and transfer
payload carries the department's field names, loaded from `events.py` rather than a copy.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "coontie.cli", *args], cwd=cwd, env=ENV, capture_output=True, text=True
    )


def first_line_id(result: subprocess.CompletedProcess) -> str:
    return result.stdout.split()[0] if result.stdout else ""


def setup(work: Path) -> None:
    init = run(
        work, "init", "--db", "ws.sqlite3", "--name", "Nature's Grace FL, LLC", "--license", "MMTC-2026-0030",
        "--street", "1200 Grove Rd", "--city", "Brooksville", "--zip", "34601",
        "--room", "inventory:INV1:01", "--room", "inventory:INV2:02",
    )
    assert init.returncode == 0, init.stderr


class TestS7Gate(unittest.TestCase):
    def test_manifest_dispatch_and_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)

            lot = first_line_id(run(work, "--db", "ws.sqlite3", "lot", "--kind", "cured and dried flower",
                                    "--cultivar", "Blue Dream", "--weight", "500", "--room", "INV1"))
            vehicle = first_line_id(run(work, "--db", "ws.sqlite3", "vehicle", "--name", "White Transit",
                                        "--plate", "FL-MMTC-12", "--make", "Ford", "--model", "Transit",
                                        "--year", "2024"))

            # The statute's crew rule, enforced in the write path.
            one_person = run(work, "--db", "ws.sqlite3", "manifest", "--recipient", "Tampa Dispensary",
                             "--address", "900 N Tampa St", "--vehicle", vehicle, "--employees", "Maria Lopez",
                             "--depart", "2026-12-15T08:00", "--arrive", "2026-12-15T11:30",
                             "--item", f"{lot}:200")
            self.assertNotEqual(one_person.returncode, 0)
            self.assertIn("381.986(8)(g)5", one_person.stderr)

            # A manifest over more than the lot holds is caught at dispatch, not silently.
            big = first_line_id(run(work, "--db", "ws.sqlite3", "manifest", "--recipient", "Tampa Dispensary",
                                    "--address", "900 N Tampa St", "--vehicle", vehicle,
                                    "--employees", "Maria Lopez; Dev Patel", "--depart", "2026-12-15T08:00",
                                    "--arrive", "2026-12-15T11:30", "--item", f"{lot}:900"))
            too_much = run(work, "--db", "ws.sqlite3", "dispatch", "--manifest", big)
            self.assertNotEqual(too_much.returncode, 0)
            self.assertIn("cannot give up more than it holds", too_much.stderr)

            built = run(work, "--db", "ws.sqlite3", "manifest", "--recipient", "Tampa Dispensary",
                        "--address", "900 N Tampa St, Tampa FL 33602", "--vehicle", vehicle,
                        "--employees", "Maria Lopez; Dev Patel", "--depart", "2026-12-15T08:00",
                        "--arrive", "2026-12-15T11:30", "--item", f"{lot}:200",
                        "--route", "SR-50 west to I-75 south", "--stop", "Brooksville facility",
                        "--stop", "Tampa Dispensary")
            self.assertEqual(built.returncode, 0, built.stderr)
            manifest = first_line_id(built)

            page_path = next((work / "reports").glob(f"manifest-{manifest}-page.txt"))
            page = page_path.read_text(encoding="utf-8")
            for letter in "abcdefg":
                self.assertIn(f"({letter})", page)
            self.assertIn("FL-MMTC-12", page)
            self.assertIn("MMTC-2026-0030", page)
            self.assertIn("Maria Lopez", page)
            self.assertIn("200 g", page)
            self.assertIn("three years", page)

            # Dispatch: real time, and the weight leaves the lot.
            dispatched = run(work, "--db", "ws.sqlite3", "dispatch", "--manifest", manifest,
                             "--at", "2026-12-15T08:05:00Z")
            self.assertEqual(dispatched.returncode, 0, dispatched.stderr)
            self.assertIn("remaining 300", dispatched.stdout)

            twice = run(work, "--db", "ws.sqlite3", "dispatch", "--manifest", manifest)
            self.assertNotEqual(twice.returncode, 0)

            # Receiving with weight unaccounted for is refused.
            short = run(work, "--db", "ws.sqlite3", "receive", "--manifest", manifest, "--receiver", "A. Reyes",
                        "--room", "INV2", "--received", f"{lot}:198")
            self.assertNotEqual(short.returncode, 0)
            self.assertIn("unaccounted", short.stderr)

            over = run(work, "--db", "ws.sqlite3", "receive", "--manifest", manifest, "--receiver", "A. Reyes",
                       "--room", "INV2", "--received", f"{lot}:250", "--rejected", f"{lot}:0")
            self.assertNotEqual(over.returncode, 0)
            self.assertIn("received against", over.stderr)

            # Under the rule, nothing is received before it is dispatched.
            pending_lot = first_line_id(run(work, "--db", "ws.sqlite3", "lot", "--kind", "cured and dried flower",
                                            "--cultivar", "Silver Haze", "--weight", "50", "--room", "INV1"))
            pending = first_line_id(run(work, "--db", "ws.sqlite3", "manifest", "--recipient", "Lab",
                                        "--address", "1 Lab Way", "--vehicle", vehicle,
                                        "--employees", "A; B", "--depart", "2026-12-16T08:00",
                                        "--arrive", "2026-12-16T09:00", "--item", f"{pending_lot}:10"))
            early = run(work, "--db", "ws.sqlite3", "receive", "--manifest", pending, "--receiver", "X",
                        "--room", "INV2")
            self.assertNotEqual(early.returncode, 0)
            self.assertIn("never dispatched", early.stderr)

            # The real receipt, with two grams refused.
            received = run(work, "--db", "ws.sqlite3", "receive", "--manifest", manifest, "--receiver", "A. Reyes",
                           "--room", "INV2", "--received", f"{lot}:198", "--rejected", f"{lot}:2",
                           "--at", "2026-12-15T11:20:00Z")
            self.assertEqual(received.returncode, 0, received.stderr)
            self.assertIn("198 g received, 2 rejected", received.stdout)

            again = run(work, "--db", "ws.sqlite3", "receive", "--manifest", manifest, "--receiver", "A. Reyes",
                        "--room", "INV2")
            self.assertNotEqual(again.returncode, 0)

            invoice = run(work, "--db", "ws.sqlite3", "invoice", "--manifest", manifest,
                          "--buyer", "Tampa Dispensary", "--seller", "Nature's Grace FL, LLC",
                          "--price", "1400", "--quantity", "198")
            self.assertEqual(invoice.returncode, 0, invoice.stderr)

            # The destination holds what arrived; the source holds what stayed.
            conn = sqlite3.connect(work / "ws.sqlite3")
            source_left = conn.execute("SELECT original FROM stock_lots WHERE id = ?", (lot,)).fetchone()[0]
            arrived = conn.execute(
                "SELECT original, room_id FROM stock_lots WHERE source_lot_id = ?", (lot,)
            ).fetchall()
            status = conn.execute("SELECT status FROM manifests WHERE id = ?", (manifest,)).fetchone()[0]
            conn.close()
            self.assertEqual(Decimal(source_left), Decimal("500"))
            self.assertEqual(len(arrived), 1)
            self.assertEqual(Decimal(arrived[0][0]), Decimal("198"))
            self.assertEqual(status, "received")

            stock = run(work, "--db", "ws.sqlite3", "stock")
            self.assertIn("300", stock.stdout)

            verify = run(work, "--db", "ws.sqlite3", "verify")
            self.assertIn("OK", verify.stdout)

    def test_transport_payloads_carry_the_departments_field_names(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)
            lot = first_line_id(run(work, "--db", "ws.sqlite3", "lot", "--kind", "cured and dried flower",
                                    "--cultivar", "Blue Dream", "--weight", "500", "--room", "INV1"))
            vehicle = first_line_id(run(work, "--db", "ws.sqlite3", "vehicle", "--plate", "FL-MMTC-12",
                                        "--make", "Ford", "--model", "Transit"))
            manifest = first_line_id(run(work, "--db", "ws.sqlite3", "manifest", "--recipient", "Tampa",
                                         "--address", "900 N Tampa St", "--vehicle", vehicle,
                                         "--employees", "A; B", "--depart", "2026-12-15T08:00",
                                         "--arrive", "2026-12-15T11:30", "--item", f"{lot}:100"))
            run(work, "--db", "ws.sqlite3", "dispatch", "--manifest", manifest)
            run(work, "--db", "ws.sqlite3", "receive", "--manifest", manifest, "--receiver", "R", "--room", "INV2")
            run(work, "--db", "ws.sqlite3", "invoice", "--manifest", manifest, "--buyer", "Tampa",
                "--seller", "Nature's Grace", "--price", "700", "--quantity", "100")

            from coontie.events import EVENTS, Stage

            wanted = {e.key: e for e in EVENTS if e.stage in (Stage.TRANSPORT, Stage.TRANSFER)}
            conn = sqlite3.connect(work / "ws.sqlite3")
            rows = conn.execute("SELECT event_key, payload FROM events").fetchall()
            conn.close()

            seen: set[str] = set()
            for key, payload_json in rows:
                if key not in wanted:
                    continue
                payload = json.loads(payload_json)
                for f in wanted[key].fields:
                    if not f.required:
                        continue  # the catalog marks these optional; a weight transfer has no unit count
                    self.assertIn(
                        f.name, payload,
                        f"{key} payload is missing the department's field {f.name!r}: {sorted(payload)}",
                    )
                seen.add(key)
            self.assertEqual(
                seen,
                {"vehicle_register", "manifest", "transfer_out", "transfer_in", "wholesale_invoice"},
                f"transport events exercised: {sorted(seen)}",
            )


if __name__ == "__main__":
    unittest.main()
