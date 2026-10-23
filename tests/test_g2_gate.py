"""G2 gate: Inventory and Lineage, checked against the record rather than against a snapshot.

The lineage assertion is the important one: the page's text must equal what `insight.lineage`
produces, line for line. If someone later "improves" the page by inventing a row, this fails.
"""

import http.cookiejar
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
sys.path.insert(0, str(ROOT / "src"))

from coontie.insight import lineage  # noqa: E402
from coontie.workspace import Facility, Product, Room, Workspace  # noqa: E402

T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(db: Path) -> dict:
    ws = Workspace(db)
    ws.add_facility(Facility(id="f1", name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030"))
    ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="f1", kind="inventory", name="INV2", number="02"))
    lot = ws.new_lot(kind="cured and dried flower", cultivar="Blue Dream", weight="600", room="inv1", at=T0)
    child = ws.split_lot(lot.id, amount="200", to_room="inv2", at=T0)
    ws.lab_sample(lot.id, weight="5", cmtl_id="ACS Laboratory", at=T0)

    product, _created = ws.add_product(Product(
        id="p1", facility_id="f1", name="Blue Dream 3.5g", product_type="Whole Flower", route="Smoking",
        upid="blue-dream-3.5-smoking-DE1114", weight_g=None, cultivar="Blue Dream",
    ))
    ws.conn.executemany(
        "INSERT INTO lots (id,product_id,room_id,quantity,unit,on_hold,created_at) VALUES (?,?,?,?,?,?,?)",
        [("lot-held", product.id, "inv1", "35", "g", 1, T0.isoformat()),
         ("lot-free", product.id, "inv1", "20", "g", 0, T0.isoformat())],
    )
    ws.conn.commit()
    ws.close()
    return {"lot": lot.id, "child": child.id, "held": "lot-held", "free": "lot-free"}


class Appliance:
    def __init__(self, db: Path):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "coontie.cli", "--db", str(db), "serve", "--port", str(self.port)],
            env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
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

    def get(self, path: str) -> tuple[int, str]:
        try:
            with self.opener.open(f"{self.base}{path}", timeout=10) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def token(self) -> str:
        for cookie in self.jar:
            if cookie.name == "coontie_session":
                return cookie.value
        return ""

    def form(self, path: str, action: str, **fields) -> tuple[int, str]:
        if not self.token():           # the cookie is minted by any page load
            self.get("/")
        payload = {"token": self.token(), "action": action}
        payload.update({f"{action}__{k}": v for k, v in fields.items()})
        try:
            with self.opener.open(
                    urllib.request.Request(f"{self.base}{path}",
                                           data=urllib.parse.urlencode(payload).encode()),
                    timeout=20) as r:
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


def lineage_block(html: str) -> str:
    m = re.search(r"<pre class='lineage'>(.*?)</pre>", html, re.S)
    if not m:
        return ""
    import html as _html

    return _html.unescape(m.group(1))


class TestG2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        self.ids = seed(self.db)
        self.app = Appliance(self.db)
        # registered here, not only in tearDown: unittest skips tearDown when setUp raises,
        # which is how 25 orphaned servers accumulated before this line existed
        self.addCleanup(self.app.stop)

    def tearDown(self):
        self.app.stop()
        self.tmp.cleanup()

    # -- inventory ----------------------------------------------------------

    def test_processing_lots_list_their_remaining_balance(self):
        status, html = self.app.get("/inventory")
        self.assertEqual(status, 200)
        text = text_of(html)
        self.assertIn(self.ids["lot"], text)
        self.assertIn("395", text)          # 600 - 200 split - 5 sampled
        self.assertIn("Blue Dream", text)
        self.assertIn("INV1", text)

    def test_a_held_product_lot_is_shown_with_its_hold(self):
        _status, html = self.app.get("/inventory")
        self.assertIn("Held product inventory", text_of(html))
        self.assertIn("on hold", text_of(html))
        self.assertIn("lot-held", html)

    def test_the_room_filter_excludes_other_rooms(self):
        _status, html = self.app.get("/inventory?room=INV2")
        text = text_of(html)
        self.assertIn(self.ids["child"], text)     # the split lot lives in INV2
        self.assertNotIn("395", text)              # the parent balance is filtered out

    def test_the_held_filter_shows_only_hold_lots(self):
        _status, html = self.app.get("/inventory?held=1")
        self.assertIn("Held product inventory", text_of(html))
        self.assertNotIn("Processing lots (", text_of(html))

    # -- lineage ------------------------------------------------------------

    def test_the_page_lineage_equals_what_the_module_produces(self):
        ws = Workspace(self.db)
        expected = "\n".join(line.render() for line in lineage(ws, self.ids["lot"]))
        ws.close()
        status, html = self.app.get(f"/inventory?lot={self.ids['lot']}")
        self.assertEqual(status, 200)
        self.assertEqual(lineage_block(html), expected)

    def test_lineage_names_the_moves_the_harvest_and_the_remaining(self):
        _status, html = self.app.get(f"/inventory?lot={self.ids['lot']}")
        block = lineage_block(html)
        self.assertIn("split: 200", block)
        self.assertIn("lab_sample: 5", block)
        self.assertIn("remaining 395", block)

    def test_selecting_a_lot_marks_its_row(self):
        _status, html = self.app.get(f"/inventory?lot={self.ids['lot']}")
        self.assertIn("tr class='picked'", html)

    def test_an_unknown_lot_is_a_404_not_a_traceback(self):
        status, body = self.app.get("/inventory?lot=stk-nope")
        self.assertEqual(status, 404)
        self.assertIn("no final product or processing lot", body)

    def test_a_lot_is_moved_from_the_inventory_screen(self):
        status, html = self.app.form("/inventory", "move", lot=self.ids["free"], room="INV2")
        self.assertEqual(status, 200)
        self.assertIn("moved to INV2", text_of(html))
        ws = Workspace(self.db)
        try:
            self.assertEqual(ws.lot(self.ids["free"]).room_id, "inv2")
        finally:
            ws.close()

    def test_a_held_lot_is_refused_a_move_on_the_screen(self):
        status, html = self.app.form("/inventory", "move", lot=self.ids["held"], room="INV2")
        self.assertEqual(status, 200)
        self.assertIn("on hold", text_of(html))

    def test_destruction_needs_the_schedule_and_the_wait(self):
        status, html = self.app.form("/inventory", "destroy", lot=self.ids["free"])
        self.assertEqual(status, 200)
        self.assertIn("schedule first", text_of(html))

        status, html = self.app.form("/inventory", "schedule_disposal", lot=self.ids["free"],
                                     reason="failed potency test")
        self.assertIn("scheduled for destruction", text_of(html))
        status, html = self.app.form("/inventory", "destroy", lot=self.ids["free"])
        self.assertEqual(status, 200)
        self.assertIn("72", text_of(html))          # the wait is what refuses it
        ws = Workspace(self.db)
        try:
            self.assertGreater(Decimal(ws.lot(self.ids["free"]).quantity), Decimal("0"))
        finally:
            ws.close()

    def test_a_lot_id_prefix_resolves(self):
        status, html = self.app.get(f"/inventory?lot={self.ids['child'][:10]}")
        self.assertEqual(status, 200)
        self.assertIn("Lineage", text_of(html))

    # -- the shell still holds ----------------------------------------------

    def test_inventory_ships_no_javascript_and_writes_nothing(self):
        before = self._events()
        status, html = self.app.get("/inventory")
        self.assertEqual(status, 200)
        self.assertNotIn("<script", html.lower())
        self.assertIn("accesskey=\"i\"", html)
        self.assertEqual(before, self._events())

    def test_a_today_finding_about_a_lot_links_to_the_inventory_screen(self):
        # seed a unit mismatch so the audit raises stock_unit_mismatch on a known lot
        ws = Workspace(self.db)
        ws.conn.execute(
            "INSERT INTO stock_moves (id,lot_id,kind,amount,unit,target_lot_id,note,at,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            ("mov-1", self.ids["lot"], "ingredient", "0", "ml", "", "", T0.isoformat(), T0.isoformat()),
        )
        ws.conn.commit()
        ws.close()
        _status, html = self.app.get("/")
        self.assertIn(f"/inventory?lot={self.ids['lot']}", html)

    def _events(self) -> int:
        conn = sqlite3.connect(self.db)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
