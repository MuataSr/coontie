"""S6 gate: harvest to final product, with the immutable expiration and conserved weight.

Two things this test insists on beyond the happy path: the ledger's processing payloads carry
the department's field names (checked against the catalog itself), and every gram is accounted
for at the end.
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
FIXTURE = ROOT / "tests" / "fixtures" / "operator_export.csv"
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
        "--room", "grow:G1:01", "--room", "inventory:DRY1:03", "--room", "inventory:INV1:04",
        "--room", "inventory:INV2:05", "--room", "inventory:EXT1:06",
    )
    assert init.returncode == 0, init.stderr
    run(work, "--db", "ws.sqlite3", "import", "--csv", str(FIXTURE))
    run(work, "--db", "ws.sqlite3", "integration", "--approved-on", "2026-09-20", "--reference", "R")


def grown_and_harvested(work: Path) -> str:
    batch = run(work, "--db", "ws.sqlite3", "batch", "--cultivar", "Blue Dream", "--room", "G1",
                "--count", "12", "--at", "2026-10-01T09:00:00Z")
    run(work, "--db", "ws.sqlite3", "plant", "--batch", first_line_id(batch), "--count", "12",
        "--at", "2026-10-02T09:00:00Z")
    run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001..PL-0012", "--schedule",
        "--at", "2026-11-18T09:00:00Z")
    harvested = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001..PL-0012",
                    "--wet", "1800", "--waste", "240", "--other", "60", "--room", "DRY1",
                    "--at", "2026-11-20T08:00:00Z")
    return first_line_id(harvested)


class TestS6Gate(unittest.TestCase):
    def test_harvest_to_final_product(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)
            harvest = grown_and_harvested(work)
            self.assertTrue(harvest.startswith("hrv-"))

            # 1. Cure.
            cure = run(work, "--db", "ws.sqlite3", "cure", "--harvest", harvest, "--post", "620",
                       "--waste", "80", "--room", "DRY1", "--at", "2026-11-28T09:00:00Z")
            self.assertEqual(cure.returncode, 0, cure.stderr)
            self.assertIn("620 g", cure.stdout)
            self.assertIn("available to allocate into lots: 620 g", cure.stdout)

            # Nothing can be cured that was never harvested.
            other = run(work, "--db", "ws.sqlite3", "harvest", "--plants", "PL-0001", "--schedule")
            self.assertNotEqual(other.returncode, 0)

            # 2. A lot bigger than the cure is refused.
            too_big = run(work, "--db", "ws.sqlite3", "lot", "--kind", "cured and dried flower",
                          "--cultivar", "Blue Dream", "--weight", "700", "--room", "INV1",
                          "--harvest", harvest, "--at", "2026-11-29T09:00:00Z")
            self.assertNotEqual(too_big.returncode, 0)
            self.assertIn("620 g cured and unallocated", too_big.stderr)

            lot = first_line_id(run(work, "--db", "ws.sqlite3", "lot", "--kind", "cured and dried flower",
                                    "--cultivar", "Blue Dream", "--weight", "600", "--room", "INV1",
                                    "--harvest", harvest, "--at", "2026-11-29T09:00:00Z"))

            # 3. Split.
            split = run(work, "--db", "ws.sqlite3", "split", "--lot", lot, "--amount", "200", "--to", "INV2",
                        "--at", "2026-12-01T09:00:00Z")
            self.assertEqual(split.returncode, 0, split.stderr)
            self.assertIn("now holds 400 g", split.stdout)

            # 4. Convert, then refuse a conversion larger than what is left.
            extract = first_line_id(run(work, "--db", "ws.sqlite3", "convert", "--lot", lot, "--remove", "300",
                                        "--to", "extract", "--resulting", "90", "--waste", "15",
                                        "--room", "EXT1", "--at", "2026-12-02T09:00:00Z"))
            over = run(work, "--db", "ws.sqlite3", "convert", "--lot", lot, "--remove", "500", "--to", "extract",
                       "--resulting", "100", "--room", "EXT1", "--at", "2026-12-03T09:00:00Z")
            self.assertNotEqual(over.returncode, 0)
            self.assertIn("cannot give up more than it holds", over.stderr)

            impossible = run(work, "--db", "ws.sqlite3", "convert", "--lot", lot, "--remove", "10",
                             "--to", "extract", "--resulting", "50", "--room", "EXT1",
                             "--at", "2026-12-03T09:00:00Z")
            self.assertNotEqual(impossible.returncode, 0)
            self.assertIn("exceeds", impossible.stderr)

            # 5. Ingredients and a lab sample.
            ingredient = run(work, "--db", "ws.sqlite3", "ingredient", "--lot", extract,
                             "--name", "MCT oil,Natural flavor", "--amount", "250,5", "--unit", "ml,ml",
                             "--at", "2026-12-04T09:00:00Z")
            self.assertEqual(ingredient.returncode, 0, ingredient.stderr)

            sample = run(work, "--db", "ws.sqlite3", "sample", "--lot", lot, "--weight", "5",
                         "--cmtl", "ACS Laboratory", "--at", "2026-12-05T09:00:00Z")
            self.assertEqual(sample.returncode, 0, sample.stderr)

            # 6. Final product, and the immutable expiration.
            conn = sqlite3.connect(work / "ws.sqlite3")
            upid = conn.execute("SELECT upid FROM products WHERE product_type='Whole Flower' LIMIT 1").fetchone()[0]
            conn.close()

            made = run(work, "--db", "ws.sqlite3", "final", "--lot", lot, "--upid", upid, "--units", "27",
                       "--net", "94.5", "--per-unit", "3.5", "--packaged", "2026-12-10",
                       "--expires", "2027-06-10", "--room", "INV1", "--at", "2026-12-10T09:00:00Z")
            self.assertEqual(made.returncode, 0, made.stderr)
            self.assertIn("expires 2027-06-10", made.stdout)

            changed = run(work, "--db", "ws.sqlite3", "final", "--lot", lot, "--upid", upid, "--units", "1",
                          "--net", "0.5", "--packaged", "2026-12-10", "--expires", "2027-09-10",
                          "--room", "INV1", "--at", "2026-12-10T10:00:00Z")
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn("immutable", changed.stderr)

            unknown = run(work, "--db", "ws.sqlite3", "final", "--lot", lot, "--upid", "not-a-product",
                          "--units", "1", "--net", "0.5", "--packaged", "2026-12-11",
                          "--expires", "2027-06-10", "--room", "INV1")
            self.assertNotEqual(unknown.returncode, 0)
            self.assertIn("not in the catalogue", unknown.stderr)

            # 7. A correction on a processing lot still drafts the 12-hour notice.
            adjust = run(work, "--db", "ws.sqlite3", "adjust", "--lot", lot, "--remove", "0.5",
                         "--cause", "spillage", "--reason", "jar knocked over during packaging",
                         "--at", "2026-12-11T09:00:00Z")
            self.assertEqual(adjust.returncode, 0, adjust.stderr)
            self.assertIn("justification drafted", adjust.stdout)

            # 8. Device inventory.
            device = run(work, "--db", "ws.sqlite3", "device", "--type", "510 thread battery",
                         "--units", "50", "--room", "INV2", "--at", "2026-12-12T09:00:00Z")
            self.assertEqual(device.returncode, 0, device.stderr)

            # 9. Weight is conserved: 600 out, and every gram is accounted for.
            stock = run(work, "--db", "ws.sqlite3", "stock")
            self.assertEqual(stock.returncode, 0, stock.stderr)
            conn = sqlite3.connect(work / "ws.sqlite3")
            moves = conn.execute("SELECT kind, amount FROM stock_moves WHERE lot_id = ?", (lot,)).fetchall()
            remaining_row = conn.execute("SELECT original FROM stock_lots WHERE id = ?", (lot,)).fetchone()
            conn.close()
            taken = sum(Decimal(m[1]) for m in moves)
            self.assertEqual(Decimal(remaining_row[0]) - taken, Decimal("0.0"))
            self.assertIn(("split", "200"), moves)
            self.assertIn(("conversion", "300"), moves)
            self.assertIn(("lab_sample", "5"), moves)
            self.assertIn(("final", "94.5"), moves)
            self.assertIn(("adjustment", "0.5"), moves)

            verify = run(work, "--db", "ws.sqlite3", "verify")
            self.assertIn("OK", verify.stdout)

    def test_processing_payloads_carry_the_departments_field_names(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            setup(work)
            harvest = grown_and_harvested(work)
            run(work, "--db", "ws.sqlite3", "cure", "--harvest", harvest, "--post", "620", "--waste", "80",
                "--room", "DRY1")
            lot = first_line_id(run(work, "--db", "ws.sqlite3", "lot", "--kind", "cured and dried flower",
                                    "--cultivar", "Blue Dream", "--weight", "600", "--room", "INV1",
                                    "--harvest", harvest))
            run(work, "--db", "ws.sqlite3", "split", "--lot", lot, "--amount", "100", "--to", "INV2")
            extract = first_line_id(run(work, "--db", "ws.sqlite3", "convert", "--lot", lot, "--remove", "300",
                                        "--to", "extract", "--resulting", "90", "--waste", "15", "--room", "EXT1"))
            run(work, "--db", "ws.sqlite3", "ingredient", "--lot", extract, "--name", "MCT oil",
                "--amount", "250", "--unit", "ml")
            run(work, "--db", "ws.sqlite3", "sample", "--lot", lot, "--weight", "5", "--cmtl", "ACS Laboratory")
            conn = sqlite3.connect(work / "ws.sqlite3")
            upid = conn.execute("SELECT upid FROM products WHERE product_type='Whole Flower' LIMIT 1").fetchone()[0]
            conn.close()
            run(work, "--db", "ws.sqlite3", "final", "--lot", lot, "--upid", upid, "--units", "10",
                "--net", "35", "--packaged", "2026-12-10", "--expires", "2027-06-10", "--room", "INV1")
            run(work, "--db", "ws.sqlite3", "device", "--type", "battery", "--units", "5", "--room", "INV2")

            from coontie.events import EVENTS, Stage

            processing = {e.key: e for e in EVENTS if e.stage is Stage.PROCESSING}
            conn = sqlite3.connect(work / "ws.sqlite3")
            rows = conn.execute("SELECT event_key, payload FROM events").fetchall()
            conn.close()

            seen: set[str] = set()
            for key, payload_json in rows:
                if key not in processing:
                    continue
                if key == "inventory_adjustment":
                    continue  # covered by the S2 gate, which has its own shape checks
                payload = json.loads(payload_json)
                for f in processing[key].fields:
                    if f.name in ("cultivar",) and key == "final_product":
                        pass
                    self.assertIn(
                        f.name, payload,
                        f"{key} payload is missing the department's field {f.name!r}: {sorted(payload)}",
                    )
                seen.add(key)
            self.assertEqual(
                seen,
                {
                    "cure_dry", "inventory_lot_create", "lot_split", "conversion",
                    "ingredient_add", "lab_sample_create", "final_product", "delivery_device_inventory",
                },
                f"processing events exercised: {sorted(seen)}",
            )


if __name__ == "__main__":
    unittest.main()
