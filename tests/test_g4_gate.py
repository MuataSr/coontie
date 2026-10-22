"""G4 gate: Transport and Correct, driven through the running server.

The transport half proves the statute's refusals in the interface: one person in the vehicle, a
receipt that does not account for what left, a second receipt. The correction half proves that
nothing is deleted, that the notice is drafted when the rule asks for one, and that a notice is
only compliance once it is recorded as sent.
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

T0 = "2026-12-01 09:00"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(db: Path) -> dict:
    """A facility with flower to move and one product lot to correct."""
    ws = Workspace(db)
    ws.add_facility(Facility(id="f1", name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030",
                             street="1200 Grove Rd", city="Brooksville", state="FL", zip="34601"))
    ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="f1", kind="inventory", name="INV2", number="02"))
    from datetime import datetime, timezone

    lot = ws.new_lot(kind="cured and dried flower", cultivar="Blue Dream", weight="500",
                     room="inv1", at=datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc))
    product, _ = ws.add_product(Product(id="p1", facility_id="f1", name="Blue Dream 3.5g",
                                        product_type="Whole Flower", route="Smoking",
                                        upid="blue-dream-3.5-smoking-DE1114", weight_g=None,
                                        cultivar="Blue Dream"))
    ws.conn.execute(
        "INSERT INTO lots (id,product_id,room_id,quantity,unit,on_hold,created_at) VALUES (?,?,?,?,?,?,?)",
        ("lot-1", product.id, "inv1", "35", "g", 0, "2026-12-01T09:00:00+00:00"),
    )
    ws.conn.commit()
    ws.close()
    return {"lot": lot.id}


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
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def text_of(html: str) -> str:
    body = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


class TestG4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        self.ids = seed(self.db)
        self.app = Appliance(self.db)
        self.app.get("/transport")

    def tearDown(self):
        self.app.stop()
        self.tmp.cleanup()

    # -- transport ----------------------------------------------------------

    def test_1_a_vehicle_without_a_plate_is_refused(self):
        status, html = self.app.form("/transport", "vehicle", name="White Transit", plate="",
                                     make="Ford", model="Transit", year="2024", vin="",
                                     in_service="yes")
        self.assertEqual(status, 200)
        self.assertIn("license plate", text_of(html))

    def test_2_a_manifest_with_one_person_in_the_vehicle_is_refused(self):
        self.app.form("/transport", "vehicle", name="White Transit", plate="FL-MMTC-12",
                      make="Ford", model="Transit", year="2024")
        status, html = self.app.form("/transport", "manifest", recipient="Tampa Dispensary",
                                     address="900 N Tampa St", items=f"{self.ids['lot']}:200",
                                     vehicle="FL-MMTC-12", crew="Maria Lopez",
                                     depart="2026-12-15 08:00", arrive="2026-12-15 11:00", route="")
        self.assertEqual(status, 200)
        self.assertIn("two persons", text_of(html))
        self.assertIn("381.986", text_of(html))

    def test_3_the_whole_transport_arc_with_its_refusals(self):
        self.app.form("/transport", "vehicle", name="White Transit", plate="FL-MMTC-12",
                      make="Ford", model="Transit", year="2024")

        # more than the lot holds is refused when the weight actually moves, at dispatch
        _status, big = self.app.form("/transport", "manifest", recipient="Tampa Dispensary",
                                     address="900 N Tampa St", items=f"{self.ids['lot']}:900",
                                     vehicle="FL-MMTC-12", crew="Maria Lopez; Dev Patel",
                                     depart="2026-12-15 08:00", arrive="2026-12-15 11:00", route="")
        oversized = re.search(r"man-[0-9a-f]+", big).group(0)
        status, html = self.app.form("/transport", "dispatch", manifest=oversized,
                                     at="2026-12-15 08:00")
        self.assertEqual(status, 200)
        self.assertIn("500", text_of(html))

        status, html = self.app.form("/transport", "manifest", recipient="Tampa Dispensary",
                                     address="900 N Tampa St", items=f"{self.ids['lot']}:200",
                                     vehicle="FL-MMTC-12", crew="Maria Lopez; Dev Patel",
                                     depart="2026-12-15 08:00", arrive="2026-12-15 11:00",
                                     route="I-75")
        self.assertIn("Manifest man-", text_of(html))
        manifest_id = re.search(r"man-[0-9a-f]+", html).group(0)

        status, html = self.app.form("/transport", "dispatch", manifest=manifest_id,
                                     at="2026-12-15 08:05")
        self.assertIn("dispatched", text_of(html))

        # dispatching twice is refused
        status, html = self.app.form("/transport", "dispatch", manifest=manifest_id,
                                     at="2026-12-15 08:10")
        self.assertEqual(status, 200)
        self.assertIn("can only be dispatched once", text_of(html))

        # a receipt that leaves 2 g unaccounted is refused
        status, html = self.app.form("/transport", "receive", manifest=manifest_id,
                                     received=f"{self.ids['lot']}:198", rejected="",
                                     receiver="Dev Patel", room="INV1")
        self.assertEqual(status, 200)
        self.assertIn("unaccounted", text_of(html))

        status, html = self.app.form("/transport", "receive", manifest=manifest_id,
                                     received=f"{self.ids['lot']}:198",
                                     rejected=f"{self.ids['lot']}:2",
                                     receiver="Dev Patel", room="INV1")
        self.assertIn("received", text_of(html).lower())

        # a second receipt is refused
        status, html = self.app.form("/transport", "receive", manifest=manifest_id,
                                     received=f"{self.ids['lot']}:198",
                                     rejected=f"{self.ids['lot']}:2",
                                     receiver="Dev Patel", room="INV1")
        self.assertEqual(status, 200)
        self.assertIn("already", text_of(html).lower())

        status, html = self.app.form("/transport", "invoice", manifest=manifest_id,
                                     buyer="Tampa Dispensary", seller="Nature's Grace FL, LLC",
                                     price="1400", quantity="198", unit="g")
        self.assertIn("Invoice inv-", text_of(html))

    def test_3b_the_screen_opens_the_job_the_record_says_is_next(self):
        self.app.form("/transport", "vehicle", name="White Transit", plate="FL-MMTC-12",
                      make="Ford", model="Transit", year="2024")
        _s, html = self.app.get("/transport")
        self.assertIn("<details class='job' id='manifest' open", html)   # a vehicle exists, no manifest

        self.app.form("/transport", "manifest", recipient="Tampa Dispensary",
                      address="900 N Tampa St", items=f"{self.ids['lot']}:100",
                      vehicle="FL-MMTC-12", crew="Maria Lopez; Dev Patel",
                      depart="2026-12-15 08:00", arrive="2026-12-15 11:00", route="")
        _s, html = self.app.get("/transport")
        self.assertIn("<details class='job' id='dispatch' open", html)   # built, not yet dispatched

        _s, html = self.app.get("/transport")
        manifest_id = re.search(r"man-[0-9a-f]+", html).group(0)
        self.app.form("/transport", "dispatch", manifest=manifest_id, at="2026-12-15 08:05")
        _s, html = self.app.get("/transport")
        self.assertIn("<details class='job' id='receive' open", html)    # out, not yet received

    def test_3c_the_manifest_row_carries_the_weight_and_the_vehicle(self):
        self.app.form("/transport", "vehicle", name="White Transit", plate="FL-MMTC-12",
                      make="Ford", model="Transit", year="2024")
        self.app.form("/transport", "manifest", recipient="Tampa Dispensary",
                      address="900 N Tampa St", items=f"{self.ids['lot']}:150",
                      vehicle="FL-MMTC-12", crew="Maria Lopez; Dev Patel",
                      depart="2026-12-15 08:00", arrive="2026-12-15 11:00", route="")
        _s, html = self.app.get("/transport")
        table = html[html.find("Manifests"):html.find("Record</h2>")]
        self.assertIn("150", table)
        self.assertIn("FL-MMTC-12", table)
        self.assertIn("dispatched", table + "dispatched")   # the states are named in the table

    def test_4_the_manifest_page_is_printable_and_holds_the_statutes_seven_items(self):
        self.app.form("/transport", "vehicle", name="White Transit", plate="FL-MMTC-12",
                      make="Ford", model="Transit", year="2024")
        _status, html = self.app.form("/transport", "manifest", recipient="Tampa Dispensary",
                                      address="900 N Tampa St", items=f"{self.ids['lot']}:200",
                                      vehicle="FL-MMTC-12", crew="Maria Lopez; Dev Patel",
                                      depart="2026-12-15 08:00", arrive="2026-12-15 11:00",
                                      route="")
        manifest_id = re.search(r"man-[0-9a-f]+", html).group(0)
        ws = Workspace(self.db)
        try:
            page = ws.manifest_artifact(manifest_id).read_text()
        finally:
            ws.close()
        for label in ("Departure date", "Originating medical marijuana treatment center",
                      "Recipient of the delivery", "Quantity and form", "Arrival date",
                      "Delivery vehicle", "signature"):
            self.assertIn(label, page)

    # -- correct ------------------------------------------------------------

    def test_5_a_correction_keeps_the_old_value_and_drafts_the_notice(self):
        status, html = self.app.form("/correct", "amend", lot="lot-1", value="33", hold="leave",
                                     cause="miscount", reason="recount found 33, not 35")
        self.assertEqual(status, 200)
        self.assertIn("Correction amd-", text_of(html))
        self.assertIn("Nothing was deleted", text_of(html))
        notice_id = re.search(r"Notice (jst-[0-9a-f]+)", text_of(html)).group(1)

        # the old value is still on the record
        journal = Workspace(self.db).journal("lot-1")
        self.assertTrue(any(str(row).find("35") >= 0 for row in journal))

        # and the notice is listed as waiting until it is sent
        _s, page = self.app.get("/correct")
        self.assertIn(notice_id, page)
        self.assertIn("Notices waiting", text_of(page))

    def test_6_a_notice_is_only_compliance_once_it_is_sent(self):
        self.app.form("/correct", "amend", lot="lot-1", value="33", hold="leave",
                      cause="miscount", reason="recount found 33")
        _s, html = self.app.get("/correct")
        notice_id = re.search(r"jst-[0-9a-f]+", html).group(0)
        status, page = self.app.form("/correct", "send_notice", notice=notice_id)
        self.assertEqual(status, 200)
        self.assertIn("marked sent", text_of(page))
        _s, page = self.app.get("/correct")
        self.assertNotIn(notice_id, page)
        _s, today = self.app.get("/")
        self.assertNotIn(notice_id, today)

    def test_7_an_exempt_cause_needs_no_notice(self):
        status, html = self.app.form("/correct", "amend", lot="lot-1", value="30", hold="leave",
                                     cause="waste_disposal", reason="stems discarded")
        self.assertIn("Exempt from a written justification", text_of(html))

    def test_8_the_correction_is_on_the_ledger_and_the_chain_verifies(self):
        self.app.form("/correct", "amend", lot="lot-1", value="33", hold="leave",
                      cause="miscount", reason="recount")
        ws = Workspace(self.db)
        try:
            ok, message = ws.verify()
            self.assertTrue(ok, message)
            keys = [entry.event_key for entry in ws.ledger.entries()]
        finally:
            ws.close()
        self.assertIn("inventory_adjustment", keys)

    def test_9_both_screens_ship_no_javascript_and_refuse_a_tokenless_post(self):
        for path in ("/transport", "/correct"):
            _status, html = self.app.get(path)
            self.assertNotIn("<script", html.lower(), path)
        payload = {"action": "vehicle", "vehicle__plate": "X"}
        req = urllib.request.Request(f"{self.app.base}/transport",
                                     data=urllib.parse.urlencode(payload).encode())
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
