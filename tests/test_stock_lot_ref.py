"""A lot reference names one lot, or it is refused.

`stock_lot()` resolved with `id == ref or id.startswith(ref)`, and `"anything".startswith("")` is True, so
a manifest line typed as `--item ":5:g"` silently shipped the first lot in the record. A prefix that
matches two lots was resolved the same way: the first one. Both are the record making a decision about
which jar leaves the building, and that decision belongs to the person holding it.
"""

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}

from coontie.workspace import Facility, Room, Workspace  # noqa: E402

NOW = datetime(2026, 12, 1, 9, tzinfo=timezone.utc)


class TestStockLotReferences(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        self.ws = Workspace(self.db)
        self.ws.add_facility(Facility(id="f1", name="Sand Pine Cultivation, LLC",
                                      license_number="MMTC-2026-0031", street="1 Grove Road",
                                      city="Brooksville", state="FL", zip="34601"))
        self.ws.add_room(Room(id="r1", facility_id="f1", kind="inventory", name="Cure", number="01"))
        self.first = self.ws.new_lot(kind="Flower", cultivar="Blue Dream", weight="600",
                                     unit="g", room="r1", at=NOW)
        self.second = self.ws.new_lot(kind="Trim", cultivar="Blue Dream", weight="300",
                                      unit="g", room="r1", at=NOW)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_an_empty_reference_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.ws.stock_lot("")
        self.assertIn("reference is required", str(caught.exception))

    def test_a_whitespace_reference_is_refused(self):
        with self.assertRaises(ValueError):
            self.ws.stock_lot("   ")

    def test_a_shared_prefix_is_refused_rather_than_guessed(self):
        with self.assertRaises(ValueError) as caught:
            self.ws.stock_lot("stk-")
        self.assertIn("matches 2 lots", str(caught.exception))

    def test_a_full_id_resolves(self):
        self.assertEqual(self.ws.stock_lot(self.first.id).id, self.first.id)

    def test_a_unique_prefix_resolves(self):
        prefix = self.second.id[:12]
        self.assertEqual(self.ws.stock_lot(prefix).id, self.second.id)


class TestTheCommandLineRefusesIt(unittest.TestCase):
    def test_a_manifest_line_with_no_lot_is_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cwd = Path(tmp.name)
        db = cwd / "ws.sqlite3"

        def run(*args, expect=None):
            result = subprocess.run([sys.executable, "-m", "coontie.cli", "--db", str(db), *args],
                                    cwd=cwd, env=ENV, capture_output=True, text=True)
            if expect is not None:
                self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
            return result

        run("init", "--name", "Sand Pine Cultivation, LLC", "--license", "MMTC-2026-0031",
            "--room", "inventory:Cure:01", expect=0)
        run("integration", "--approved-on", "2026-10-01", "--reference", "letter", expect=0)
        run("vehicle", "--plate", "FL-MMTC31", "--make", "Ford", "--model", "Transit", "--year", "2024",
            expect=0)
        vehicle = subprocess.run(
            [sys.executable, "-c",
             "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
             "print(c.execute('select id from vehicles limit 1').fetchone()[0])", str(db)],
            capture_output=True, text=True).stdout.strip()

        refused = run("manifest", "--recipient", "Sand Pine Dispensary", "--address", "2200 Main Street",
                      "--vehicle", vehicle, "--employees", "Ana Ruiz,Marcus Bell",
                      "--depart", "2026-12-02T08:00", "--arrive", "2026-12-02T11:00",
                      "--item", ":5:g")
        self.assertEqual(refused.returncode, 1, "a manifest line with no lot must not build")
        self.assertIn("reference is required", refused.stdout + refused.stderr)
        count = subprocess.run(
            [sys.executable, "-c",
             "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
             "print(c.execute('select count(*) from manifests').fetchone()[0])", str(db)],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(count, "0", "and nothing may be written")


if __name__ == "__main__":
    unittest.main()
