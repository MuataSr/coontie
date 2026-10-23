"""G1 gate: the appliance shell, Today, and Say it — over real HTTP, with the ledger watched.

The point of this test is that the interface is proved the way an operator uses it: a browser
posts a form, the server answers, and the record is checked afterwards. Nothing here calls a
render function directly except the escaping checks.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed(db: Path) -> None:
    """A facility with one finding (an adjustment with no justification) and a manifest."""
    sys.path.insert(0, str(ROOT / "src"))
    from coontie.workspace import Facility, Room, Workspace

    ws = Workspace(db)
    ws.add_facility(Facility(id="f1", name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030",
                             street="1200 Grove Rd", city="Brooksville", state="FL", zip="34601"))
    ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="f1", kind="inventory", name="INV2", number="02"))
    lot = ws.new_lot(kind="cured and dried flower", cultivar="Blue Dream", weight="500", room="inv1",
                     at=datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc))
    _amendment, justification = ws.adjust_stock(lot.id, remove="2", cause="spillage",
                                                reason="jar knocked over",
                                                at=datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc))
    ws.conn.execute("DELETE FROM justifications WHERE id = ?", (justification.id,))
    ws.conn.commit()
    vehicle = ws.register_vehicle(name="White Transit", plate="FL-MMTC-12", make="Ford", model="Transit")
    manifest = ws.build_manifest(recipient_name="Tampa Dispensary", recipient_address="900 N Tampa St",
                      vehicle=vehicle.id, employee_ids=("Maria Lopez", "Dev Patel"),
                      departure_at=datetime(2026, 12, 15, 8, 0, tzinfo=timezone.utc),
                      arrival_at=datetime(2026, 12, 15, 11, 0, tzinfo=timezone.utc),
                      items=[(lot.id, "200", "")], at=datetime(2026, 12, 15, 7, 0, tzinfo=timezone.utc))
    ws.dispatch_manifest(manifest.id, at=datetime(2026, 12, 15, 8, 5, tzinfo=timezone.utc))
    ws.close()


class Appliance:
    """A server in a subprocess, driven the way a browser drives it."""

    def __init__(self, db: Path):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "coontie.cli", "--db", str(db), "serve", "--port", str(self.port)],
            env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
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

    def headers(self, path: str = "/") -> dict:
        with self.opener.open(f"{self.base}{path}", timeout=10) as r:
            return dict(r.headers)

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

    def post(self, path: str, fields: dict, *, origin: str | None = None,
             token: str | None = None) -> tuple[int, str]:
        data = dict(fields)
        if token is not False:
            data["token"] = self.token() if token is None else token
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(f"{self.base}{path}", data=body)
        if origin:
            req.add_header("Origin", origin)
        try:
            with self.opener.open(req, timeout=10) as r:
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


class TestG1(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        seed(self.db)
        self.app = Appliance(self.db)
        # registered here, not only in tearDown: unittest skips tearDown when setUp raises,
        # which is how 25 orphaned servers accumulated before this line existed
        self.addCleanup(self.app.stop)
        status, _body = self.app.get("/")
        self.assertEqual(status, 200)

    def tearDown(self):
        self.app.stop()
        self.tmp.cleanup()

    # -- the shell ----------------------------------------------------------

    def test_the_rail_carries_text_labels_and_access_keys(self):
        status, html = self.app.get("/")
        self.assertEqual(status, 200)
        for label in ("Today", "Say it", "Inventory", "Plant", "Process", "Transport",
                      "Correct", "Drift", "Audit", "Setup"):
            self.assertIn(label, html)
        self.assertIn('accesskey="t"', html)
        self.assertIn('accesskey="i"', html)

    def test_the_session_cookie_is_http_only_and_strict(self):
        self.app.jar.clear()
        with urllib.request.urlopen(f"{self.app.base}/") as r:
            cookie = r.headers.get("Set-Cookie") or ""
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("coontie_session=", cookie)

    def test_pages_carry_a_content_security_policy_and_ship_no_javascript(self):
        status, html = self.app.get("/")
        self.assertEqual(status, 200)
        self.assertNotIn("<script", html.lower())
        csp = self.app.headers().get("Content-Security-Policy", "")
        self.assertIn("form-action 'self'", csp)
        self.assertIn("default-src 'none'", csp)

    def test_the_print_stylesheet_hides_the_chrome(self):
        _status, html = self.app.get("/")
        media = html[html.find("@media print"):]
        self.assertIn("@media print", html)
        self.assertIn("display:none", media)
        self.assertIn("nav", media)

    # -- Today --------------------------------------------------------------

    def test_today_shows_the_seeded_breach_with_its_citation(self):
        _status, html = self.app.get("/")
        text = text_of(html)
        self.assertIn("Today", text)
        self.assertIn("has no written justification drafted", text)
        self.assertIn("64-4.222(12)", text)

    def test_today_shows_the_manifest_that_is_still_out(self):
        _status, html = self.app.get("/")
        self.assertIn("is still out", text_of(html))

    def test_today_shows_a_weekly_sentence_not_a_chart(self):
        _status, html = self.app.get("/")
        text = text_of(html)
        self.assertIn("This week", text)
        self.assertIn("were written in the 7 days to", text)
        self.assertNotIn("<svg", html)

    def test_a_finding_links_to_its_screen_once_that_screen_exists(self):
        _status, html = self.app.get("/")
        body = html[html.find("<main>"):html.find("</main>")]
        # the stock finding now links: Inventory is built
        self.assertIn('<a href="/inventory?lot=', body)
        # the correction finding still names a command: the Correct screen is not built yet
        row = body[body.find("no written justification"):]
        row = row[:row.find("</li>")]
        self.assertIn("coontie justifications", row)
        self.assertNotIn("<a", row)

    def test_today_states_what_the_record_cannot_check(self):
        _status, html = self.app.get("/audit")
        text = text_of(html)
        self.assertIn("What this cannot check", text)
        self.assertIn("MMUR", text)

    # -- Say it -------------------------------------------------------------

    def test_say_it_parses_a_sentence_and_echoes_the_command_without_writing(self):
        before = self._events()
        status, html = self.app.post("/say", {"sentence":
                                   "send 200 g blue dream to tampa with maria and dev"})
        self.assertEqual(status, 200)
        text = text_of(html)
        self.assertIn("What that means", text)
        self.assertIn("manifest", text)
        self.assertIn("--item", text)
        self.assertIn("nothing written", text)
        self.assertEqual(before, self._events(), "Say it must not write to the record")

    def test_say_it_resolves_a_crew_from_previous_manifests(self):
        _status, html = self.app.post("/say", {"sentence": "send 50 g blue dream to tampa with maria"})
        self.assertIn("Maria Lopez", html)

    def test_say_it_refuses_a_sentence_it_cannot_read_and_says_why(self):
        _status, html = self.app.post("/say", {"sentence": "what happened to blue dream last week"})
        text = text_of(html)
        self.assertIn("no verb I know", text)

    def test_say_it_escapes_what_the_operator_typed(self):
        _status, html = self.app.post("/say", {"sentence": "<script>alert(1)</script>"})
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    # -- security -----------------------------------------------------------

    def test_a_post_without_the_session_token_is_refused(self):
        status, _body = self.app.post("/say", {"sentence": "audit"}, token=False)
        self.assertEqual(status, 403)

    def test_a_post_with_the_wrong_token_is_refused(self):
        status, _body = self.app.post("/say", {"sentence": "audit"}, token="not-the-token")
        self.assertEqual(status, 403)

    def test_a_post_from_another_origin_is_refused(self):
        status, _body = self.app.post("/say", {"sentence": "audit"}, origin="https://evil.example")
        self.assertEqual(status, 403)

    def test_a_request_with_a_foreign_host_is_refused(self):
        req = urllib.request.Request(f"{self.app.base}/")
        req.add_header("Host", "evil.example")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)

    def test_the_operator_name_is_recorded_as_a_claim_not_a_credential(self):
        status, _body = self.app.post("/operator", {"operator": "Maria Lopez"})
        self.assertEqual(status, 200)
        names = [urllib.parse.unquote(c.value) for c in self.app.jar if c.name == "coontie_operator"]
        self.assertEqual(names, ["Maria Lopez"])
        _s, html = self.app.get("/")
        self.assertIn("Maria Lopez", html)

    # -- helpers ------------------------------------------------------------

    def _events(self) -> int:
        conn = sqlite3.connect(self.db)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
