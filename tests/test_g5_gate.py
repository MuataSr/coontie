"""G5 gate: Setup, Audit and the things that get printed.

Setup is where a new licensee starts, so the import is tested the way it will be used: a dry run
that writes nothing, then a real run, then the catalogue download. Audit is tested for the two
things that make it trustworthy: it carries every finding with its citation, and it says out loud
what it cannot check. And the ledger check is tested by breaking the chain.
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

from coontie.workspace import Workspace  # noqa: E402

CSV = """Product Name,Product Type,Route of Administration,Cultivar or Strain Name,Product Weight,THC Weight
Blue Dream 3.5g,Whole Flower,Smoking,Blue Dream,3.5,0.62
Nightshade Gummies 10pk,Gelatin,Oral,Nightshade,50,5
Broken Row,Whole Flower,Smoking,,not-a-number,1
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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

    def get_headers(self, path: str) -> tuple[int, dict, str]:
        with self.opener.open(f"{self.base}{path}", timeout=15) as r:
            return r.status, dict(r.headers), r.read().decode()

    def form(self, path: str, action: str, **fields) -> tuple[int, str]:
        payload = {"token": self.token(), "action": action}
        payload.update({f"{action}__{k}": v for k, v in fields.items()})
        try:
            with self.opener.open(
                    urllib.request.Request(f"{self.base}{path}",
                                           data=urllib.parse.urlencode(payload).encode()),
                    timeout=25) as r:
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


class TestG5(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        self.app = Appliance(self.db)
        self.app.get("/setup")

    def tearDown(self):
        self.app.stop()
        self.tmp.cleanup()

    # -- setup --------------------------------------------------------------

    def test_1_an_empty_workspace_asks_for_the_facility_first(self):
        _status, html = self.app.get("/setup")
        text = text_of(html)
        self.assertIn("No facility is recorded yet", text)
        self.assertIn("<details class='job' id='facility' open", html)

    def test_2_a_room_kind_the_schema_forbids_is_refused_with_the_rule(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC",
                      license="MMTC-2026-0030", street="1200 Grove Rd", city="Brooksville",
                      state="FL", zip="34601")
        status, html = self.app.form("/setup", "room", kind="cure", name="C1", number="01",
                                     quarantine="no")
        self.assertEqual(status, 200)
        self.assertIn("grow room or an inventory room", text_of(html))

    def test_3_rooms_are_added_and_listed(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC", license="MMTC-2026-0030")
        status, html = self.app.form("/setup", "room", kind="grow", name="G1", number="01",
                                     quarantine="no")
        self.assertIn("Room G1 added as a grow room", text_of(html))
        self.app.form("/setup", "room", kind="inventory", name="INV1", number="02", quarantine="no")
        _s, page = self.app.get("/setup")
        self.assertIn("Rooms (2)", text_of(page))

    def test_4_an_import_dry_run_writes_nothing_and_shows_what_failed(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC", license="MMTC-2026-0030")
        ws = Workspace(self.db)
        ws.add_room(__import__("coontie.workspace", fromlist=["Room"]).Room(
            id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
        before = len(ws.products())
        ws.close()

        status, html = self.app.form("/setup", "import", csv=CSV)
        self.assertEqual(status, 200)
        text = text_of(html)
        self.assertIn("would import", text)
        self.assertIn("1 failed", text)
        ws = Workspace(self.db)
        try:
            self.assertEqual(len(ws.products()), before, "a dry run must not write products")
        finally:
            ws.close()

    def test_5_the_real_import_writes_the_products_and_the_catalogue_downloads(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC", license="MMTC-2026-0030")
        ws = Workspace(self.db)
        from coontie.workspace import Room

        ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
        ws.close()

        status, html = self.app.form("/setup", "import", csv=CSV, go="1")
        self.assertEqual(status, 200)
        text = text_of(html)
        self.assertIn("imported 2/3", text)
        self.assertIn("row 4", text)          # the broken row is named by line number
        self.assertIn("Read as", text)        # and the column mapping is shown

        ws = Workspace(self.db)
        try:
            self.assertEqual(len(ws.products()), 2)
        finally:
            ws.close()

        status, headers, body = self.app.get_headers("/setup/catalogue.csv")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        self.assertIn("text/csv", headers.get("Content-Type", ""))
        header = body.splitlines()[0]
        for column in ("Product Type", "Unique Product ID", "Product Weight", "Approval Date"):
            self.assertIn(column, header)
        self.assertEqual(len(body.strip().splitlines()), 3)   # header plus two products

    def test_5b_an_employee_and_an_api_user_are_recorded_without_storing_the_password(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC", license="MMTC-2026-0030")
        status, html = self.app.form("/setup", "employee", name="Maria Lopez", dob="1990-04-02",
                                     hired="2026-01-05", email="maria@example.com")
        self.assertEqual(status, 200)
        self.assertIn("Maria Lopez", html)
        self.assertIn("Employees (1)", text_of(html))
        self.assertNotIn("1990-04-02", text_of(html))     # the birth date is not displayed back

        # a second record for the same person is refused in the rule's words
        status, html = self.app.form("/setup", "employee", name="Maria Lopez", dob="1990-04-02",
                                     hired="2026-01-05", email="maria@example.com")
        self.assertIn("already an employee", text_of(html))

        secret = "correct horse battery staple"
        status, html = self.app.form("/setup", "api_user", email="robot@example.com",
                                     password=secret, permissions="inventory.read")
        self.assertEqual(status, 200)
        self.assertIn("verifier", text_of(html))
        self.assertIn("robot@example.com", html)
        raw = self.db.read_bytes()
        self.assertNotIn(secret.encode(), raw)
        self.assertNotIn(secret, html)

    def test_6_verify_reports_the_chain_and_a_broken_chain_is_not_hidden(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC", license="MMTC-2026-0030")
        status, html = self.app.get("/setup?verify=1")
        self.assertIn("Verified", text_of(html))

        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE events SET payload = '{}' WHERE rowid = 1")
        conn.commit()
        conn.close()

        status, html = self.app.get("/setup?verify=1")
        self.assertIn("BROKEN", text_of(html))
        _s, audit = self.app.get("/audit")
        self.assertIn("Ledger broken", text_of(audit))

    # -- audit --------------------------------------------------------------

    def test_7_audit_carries_every_finding_with_its_citation(self):
        from datetime import datetime, timezone

        from coontie.workspace import Facility, Room, Workspace as WS

        ws = WS(self.db)
        ws.add_facility(Facility(id="f1", name="Nature's Grace FL, LLC",
                                 license_number="MMTC-2026-0030"))
        ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
        ws.new_lot(kind="cured and dried flower", cultivar="Blue Dream", weight="100",
                   room="inv1", at=datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc))
        ws.close()
        _status, html = self.app.get("/audit")
        text = text_of(html)
        self.assertIn("Audit", text)
        self.assertIn("What this cannot check", text)
        self.assertIn("MMUR", text)
        self.assertIn("64-4.222(11)", text)     # a lot with no origin is a finding on a bare facility

    def test_8_audit_prints_a_heading_a_license_and_the_counts(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC", license="MMTC-2026-0030",
                      street="1200 Grove Rd", city="Brooksville", state="FL", zip="34601")
        _status, html = self.app.get("/audit")
        import html as _html

        start = html.find("class='printonly'")
        block = _html.unescape(html[start:html.find("</div>", start)])
        self.assertIn("Compliance audit", block)
        self.assertIn("Nature's Grace FL, LLC", block)
        self.assertIn("MMTC-2026-0030", block)
        self.assertIn("ledger verified", block)
        self.assertIn(".printonly { display:block !important; }", html)

    def test_8b_the_print_block_carries_evidence_not_only_a_claim(self):
        self.app.form("/setup", "facility", name="Nature's Grace FL, LLC", license="MMTC-2026-0030")
        _s, html = self.app.get("/audit")
        self.assertRegex(html, r"hash chain head <code>[0-9a-f]{32}")
        self.assertIn("Inspected by", html)
        self.assertIn("print-color-adjust", html)   # emphasis survives a black and white printer

    def test_9_neither_screen_ships_javascript_and_a_tokenless_post_is_refused(self):
        for path in ("/setup", "/audit"):
            _status, html = self.app.get(path)
            self.assertNotIn("<script", html.lower(), path)
        payload = {"action": "facility", "facility__name": "X"}
        req = urllib.request.Request(f"{self.app.base}/setup",
                                     data=urllib.parse.urlencode(payload).encode())
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
