"""G3 gate: the Plant and Process screens, driven the way an operator drives them.

This walks a full arc through the running server: integration, batch, plants, move, schedule,
harvest, cure, lot, split, convert, sample, final product, correction. Every refusal the record is
capable of producing on this path is asserted once, in the words the rule uses.
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}

from coontie.workspace import Facility, Product, Room, Workspace  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(db: Path) -> None:
    ws = Workspace(db)
    ws.add_facility(Facility(id="f1", name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030"))
    for index, (rid, name, kind) in enumerate(
            (("g1", "G1", "grow"), ("flw1", "FLW1", "grow"), ("c1", "C1", "inventory"),
             ("inv1", "INV1", "inventory"), ("inv2", "INV2", "inventory"),
             ("ext1", "EXT1", "inventory")), start=1):
        ws.add_room(Room(id=rid, facility_id="f1", kind=kind, name=name, number=f"{index:02d}"))
    # the catalogue arrives by import or from Setup; a final product cannot name a UPID that is
    # not in it, so the fixture carries one product the way an import would have left it
    ws.add_product(Product(id="p1", facility_id="f1", name="Blue Dream 3.5g", product_type="Whole Flower",
                           route="Smoking", upid="blue-dream-3.5-smoking-DE1114", weight_g=None,
                           cultivar="Blue Dream"))
    ws.close()


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
        raise RuntimeError("server did not start")

    def token(self) -> str:
        for cookie in self.jar:
            if cookie.name == "coontie_session":
                return cookie.value
        return ""

    def get(self, path: str) -> tuple[int, str]:
        try:
            with self.opener.open(f"{self.base}{path}", timeout=15) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def form(self, path: str, action: str, **fields) -> tuple[int, str]:
        """Post one form the way the browser does: token, action, then the named fields."""
        payload = {"token": self.token(), "action": action}
        payload.update({f"{action}__{k}": v for k, v in fields.items()})
        body = urllib.parse.urlencode(payload).encode()
        try:
            with self.opener.open(urllib.request.Request(f"{self.base}{path}", data=body),
                                  timeout=20) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def text_of(html: str) -> str:
    body = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


class TestG3(unittest.TestCase):
    """One arc, in order, because the record is a sequence of events and not a set of fields."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        seed(self.db)
        self.app = Appliance(self.db)
        self.app.get("/plant")            # sets the session cookie

    def tearDown(self):
        self.app.stop()
        self.tmp.cleanup()

    # -- plant --------------------------------------------------------------

    def test_1_cultivation_is_refused_before_the_integration_is_recorded(self):
        status, html = self.app.form("/plant", "batch", cultivar="Blue Dream", room="G1", count="12")
        self.assertEqual(status, 200)                       # a refusal re-renders, it does not 500
        self.assertIn("64-4.221(4)", text_of(html))
        self.assertIn("cannot start before integration", text_of(html))

    def test_2_the_integration_is_recorded_and_the_refusal_goes_away(self):
        status, html = self.app.form("/plant", "integration", approved_on="2026-03-14",
                                     reference="DOH-PLAN-0031", note="")
        self.assertEqual(status, 200)
        self.assertIn("Integration recorded", text_of(html))
        _s, page = self.app.get("/plant")
        self.assertNotIn("No integration plan is recorded", text_of(page))

    def test_3_a_batch_plants_and_refuses_more_plants_than_it_holds(self):
        self.app.form("/plant", "integration", approved_on="2026-03-14", reference="P-1")
        status, html = self.app.form("/plant", "batch", cultivar="Blue Dream", room="G1", count="12")
        self.assertEqual(status, 200)
        self.assertIn("started: 12 x Blue Dream", text_of(html))
        batch_id = re.search(r"bat-[0-9a-f]+", html).group(0)

        status, html = self.app.form("/plant", "plant", batch=batch_id, count="12", mother="no")
        self.assertIn("Planted 12", text_of(html))
        status, html = self.app.form("/plant", "plant", batch=batch_id, count="1", mother="no")
        self.assertEqual(status, 200)
        self.assertIn("too many", text_of(html))

    def test_4_a_move_and_a_schedule_then_a_harvest(self):
        self.app.form("/plant", "integration", approved_on="2026-03-14", reference="P-1")
        _s, html = self.app.form("/plant", "batch", cultivar="Blue Dream", room="G1", count="12")
        batch_id = re.search(r"bat-[0-9a-f]+", html).group(0)
        self.app.form("/plant", "plant", batch=batch_id, count="12", mother="no")

        status, html = self.app.form("/plant", "move", plants="PL-0001..PL-0004", room="FLW1")
        self.assertIn("Moved 4 plants to FLW1", text_of(html))

        status, html = self.app.form("/plant", "additive", plants="PL-0001..PL-0004",
                                     description="Neem oil 1.5%", amount="12", unit="ml")
        self.assertIn("Additive", text_of(html))

        status, html = self.app.form("/plant", "schedule", plants="PL-0005..PL-0012")
        self.assertIn("scheduled for 8 plants", text_of(html))

        # a plant that is not on a schedule cannot be harvested
        status, html = self.app.form("/plant", "harvest", plants="PL-0001..PL-0004", wet="600",
                                     waste="40", other="10", post_room="C1")
        self.assertEqual(status, 200)
        self.assertIn("schedule", text_of(html).lower())

        status, html = self.app.form("/plant", "harvest", plants="PL-0005..PL-0012", wet="1800",
                                     waste="240", other="60", post_room="C1")
        self.assertIn("Harvest hrv-", text_of(html))
        self.assertIn("1800", text_of(html))

    def _to_harvest(self) -> str:
        self.app.form("/plant", "integration", approved_on="2026-03-14", reference="P-1")
        _s, html = self.app.form("/plant", "batch", cultivar="Blue Dream", room="G1", count="12")
        batch_id = re.search(r"bat-[0-9a-f]+", html).group(0)
        self.app.form("/plant", "plant", batch=batch_id, count="12", mother="no")
        self.app.form("/plant", "schedule", plants="PL-0001..PL-0012")
        _s, html = self.app.form("/plant", "harvest", plants="PL-0001..PL-0012", wet="1800",
                                 waste="240", other="60", post_room="C1")
        return re.search(r"hrv-[0-9a-f]+", html).group(0)

    def test_4b_an_uncured_harvest_is_offered_by_name_not_remembered(self):
        harvest_id = self._to_harvest()
        _status, html = self.app.get("/process")
        self.assertIn(f"value='{harvest_id}'", html.replace('"', "'"))

    # -- process ------------------------------------------------------------

    def test_5_processing_arc_with_every_refusal_on_the_path(self):
        harvest_id = self._to_harvest()

        # a cure of more than the wet weight is refused
        status, html = self.app.form("/process", "cure", harvest=harvest_id, post="2000",
                                     waste="0", room="C1")
        self.assertEqual(status, 200)
        self.assertIn("1800", text_of(html))
        status, html = self.app.form("/process", "cure", harvest=harvest_id, post="620",
                                     waste="80", room="C1")
        self.assertIn("Cured to 620", text_of(html))

        # curing the same harvest twice is refused, and the refusal says when it was cured
        status, html = self.app.form("/process", "cure", harvest=harvest_id, post="600",
                                     waste="0", room="C1")
        self.assertEqual(status, 200)
        self.assertIn("was already cured to 620", text_of(html))
        self.assertIn("a harvest is cured once", text_of(html))

        # a lot cannot take more than the harvest has cured
        status, html = self.app.form("/process", "lot", kind="cured and dried flower",
                                     cultivar="Blue Dream", weight="700", room="INV1",
                                     harvest=harvest_id)
        self.assertIn("620", text_of(html))
        status, html = self.app.form("/process", "lot", kind="cured and dried flower",
                                     cultivar="Blue Dream", weight="600", room="INV1",
                                     harvest=harvest_id)
        self.assertIn("Lot stk-", text_of(html))
        lot_id = re.search(r"stk-[0-9a-f]+", html).group(0)

        # split, then a split of more than the lot holds
        status, html = self.app.form("/process", "split", lot=lot_id, amount="200", room="INV2")
        self.assertIn("Split 200", text_of(html))
        status, html = self.app.form("/process", "split", lot=lot_id, amount="900", room="INV2")
        self.assertEqual(status, 200)
        self.assertIn("900", text_of(html))

        # conversion conserves weight, and cannot remove more than the lot holds
        status, html = self.app.form("/process", "convert", lot=lot_id, remove="300", kind="extract",
                                     result="90", waste="15", room="EXT1")
        self.assertIn("Converted into stk-", text_of(html))
        status, html = self.app.form("/process", "convert", lot=lot_id, remove="900", kind="extract",
                                     result="200", waste="0", room="EXT1")
        self.assertEqual(status, 200)
        self.assertIn("cannot give up more than it holds", text_of(html))

        # ingredients, a lab sample, a final product
        status, html = self.app.form("/process", "ingredients", lot=lot_id,
                                     names="MCT oil, Natural flavor", amounts="250, 5",
                                     units="ml, ml")
        self.assertIn("Ingredients recorded", text_of(html))
        # the unallocated balance must never go negative after a split, a conversion or a sample
        _s, page = self.app.get("/process")
        block = re.search(r"Cured harvests.*?Record", text_of(page)).group(0)
        self.assertIsNone(re.search(r"\s-\d", block), block)
        self.assertIn("20 g", block)     # 620 cured, 600 allocated to the lot
        status, html = self.app.form("/process", "sample", lot=lot_id, weight="5",
                                     lab="ACS Laboratory")
        self.assertIn("Sample lab-", text_of(html))

        status, html = self.app.form("/process", "final", lot=lot_id,
                                     upid="blue-dream-3.5-smoking-DE1114", units="27", net="94.5",
                                     packaged_at="2026-12-10 09:00", expiration="2027-06-10",
                                     room="INV1")
        self.assertIn("Final product blue-dream-3.5-smoking-DE1114", text_of(html))

        # recording the same product with a different expiration is refused, in the catalogue's words
        status, html = self.app.form("/process", "final", lot=lot_id,
                                     upid="blue-dream-3.5-smoking-DE1114", units="1", net="3.5",
                                     packaged_at="2026-12-10 09:00", expiration="2027-01-01",
                                     room="INV1")
        self.assertEqual(status, 200)
        self.assertIn("immutable once recorded", text_of(html))

        # a correction drafts the notice, and says when it is due
        status, html = self.app.form("/process", "adjust", lot=lot_id, remove="0.5",
                                     cause="spillage", reason="jar knocked over during packaging")
        self.assertIn("Correction amd-", text_of(html))
        self.assertIn("drafted", text_of(html))

    def test_6_an_exempt_cause_records_no_notice(self):
        harvest_id = self._to_harvest()
        self.app.form("/process", "cure", harvest=harvest_id, post="620", waste="80", room="C1")
        _s, html = self.app.form("/process", "lot", kind="cured and dried flower",
                                 cultivar="Blue Dream", weight="600", room="INV1",
                                 harvest=harvest_id)
        lot_id = re.search(r"stk-[0-9a-f]+", html).group(0)
        status, html = self.app.form("/process", "adjust", lot=lot_id, remove="15",
                                     cause="waste_disposal", reason="stems and fan leaves")
        self.assertIn("Exempt from a written justification", text_of(html))

    # -- the record still holds ---------------------------------------------

    def test_7_the_whole_arc_is_on_the_ledger_and_the_chain_verifies(self):
        self._to_harvest()
        ws = Workspace(self.db)
        try:
            ok, message = ws.verify()
            self.assertTrue(ok, message)
            appended = [entry.event_key for entry in ws.ledger.entries()]
        finally:
            ws.close()
        for expected in ("integration_approved", "seed_clone_batch", "immature_plant",
                         "harvest_schedule", "harvest"):
            self.assertIn(expected, appended)

    def test_7b_the_cause_is_a_list_not_a_memory_test(self):
        _status, html = self.app.get("/process")
        self.assertIn("<select id='adjust_cause'", html.replace('"', "'"))
        self.assertIn("waste_disposal (no notice needed)", html)
        self.assertIn("spillage", html)

    def test_8_a_form_posted_without_the_token_is_refused(self):
        payload = {"action": "batch", "batch__cultivar": "X", "batch__room": "G1",
                   "batch__count": "1"}
        req = urllib.request.Request(f"{self.app.base}/plant",
                                     data=urllib.parse.urlencode(payload).encode())
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)

    def test_9_the_screens_ship_no_javascript(self):
        for path in ("/plant", "/process"):
            _status, html = self.app.get(path)
            self.assertNotIn("<script", html.lower(), path)
            self.assertIn("name='token'", html.replace('"', "'"), path)


if __name__ == "__main__":
    unittest.main()
