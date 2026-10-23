"""The LAN gate: a record that leaves loopback has to know who is allowed in.

Every test here runs against a real server on a real socket, because the thing being tested is a
boundary and a stub cannot hold one.
"""

import http.cookiejar
import socket
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from coontie import devices, web
from coontie.workspace import Facility, Workspace

sys.path.insert(0, str(Path(__file__).parent))
import test_g4_gate as g4  # noqa: E402

NOW = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def seed(db: Path) -> None:
    g4.seed(db)


class Server:
    """A server on a given address, with a cookie jar that behaves like a browser's."""

    def __init__(self, db: Path, *, lan: bool, host: str = "127.0.0.1"):
        self.port = free_port()
        self.host = host
        self.httpd = web.serve(db, port=self.port, host=host, lan=lan)
        import threading

        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    @property
    def base(self) -> str:
        return f"http://{self.host}:{self.port}"

    def wait(self) -> None:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{self.base}/health", timeout=1) as r:
                    if r.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.05)
        raise RuntimeError("server did not start")

    def _opener(self, follow: bool):
        handlers = [urllib.request.HTTPCookieProcessor(self.jar)]
        if not follow:
            handlers.append(NoRedirect())
        return urllib.request.build_opener(*handlers)

    def get(self, path: str, *, follow: bool = True):
        opener = self._opener(follow)
        try:
            with opener.open(f"{self.base}{path}", timeout=5) as r:
                return r.status, r.read().decode(), r.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(), exc.headers

    def post(self, path: str, fields: dict, *, origin: str | None = None):
        body = urllib.parse.urlencode(fields).encode()
        request = urllib.request.Request(f"{self.base}{path}", data=body, method="POST")
        if origin:
            request.add_header("Origin", origin)
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            # a redirect is the answer being tested, so never follow one here
            with self._opener(False).open(request, timeout=5) as r:
                return r.status, r.read().decode(), r.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode(), exc.headers

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class LanCase(unittest.TestCase):
    lan = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.close()
        self.ws.close()
        self.tmp.cleanup()

    def start(self, *, lan: bool | None = None, host: str = "127.0.0.1"):
        self.server = Server(self.db, lan=self.lan if lan is None else lan, host=host)
        self.server.wait()
        return self.server


class TestLoopbackIsUnchanged(LanCase):
    lan = False

    def test_loopback_still_needs_no_terminal(self):
        server = self.start()
        status, body, _ = server.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Today", body)

    def test_loopback_still_refuses_a_foreign_origin_on_a_post(self):
        server = self.start()
        status, body, _ = server.post("/operator", {"operator": "Maria", "token": self.server_httpd_token()},
                                      origin="http://evil.example")
        self.assertEqual(status, 403)

    def server_httpd_token(self) -> str:
        return self.server.httpd.RequestHandlerClass.app.token


class TestLanGate(LanCase):
    def test_a_lan_build_with_nothing_paired_is_refused(self):
        with self.assertRaises(SystemExit) as ctx:
            web.serve(self.db, port=free_port(), lan=True)
        self.assertIn("no terminal is registered", str(ctx.exception))

    def test_an_unpaired_request_is_sent_to_the_pair_page(self):
        devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        status, body, headers = server.get("/", follow=False)
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/pair")
        status, body, _ = server.get("/pair")
        self.assertEqual(status, 200)
        self.assertIn("Pair this device", body)

    def test_health_answers_unpaired_and_says_nothing_else(self):
        devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        status, body, _ = server.get("/health", follow=False)
        self.assertEqual((status, body), (200, "ok"))

    def test_a_correct_code_pairs_once_and_the_cookie_opens_the_record(self):
        device, code = devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        status, body, headers = server.post("/pair", {"code": code})
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/")
        status, body, _ = server.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Today", body)
        # the same code a second time is refused, in a browser that has forgotten its cookie
        fresh = Server(self.db, lan=True)
        fresh.wait()
        try:
            status, body, headers = fresh.post("/pair", {"code": code})
            self.assertEqual(status, 303)
            self.assertIn("error=", headers["Location"] or "")
            status, body, _ = fresh.get("/", follow=False)
            self.assertEqual(status, 303)
        finally:
            fresh.close()

    def test_a_code_with_spaces_and_lowercase_still_works(self):
        device, code = devices.add_device(self.ws, "tablet", actor="Maria", at=NOW)
        server = self.start()
        friendly = f"{code[:5].lower()} {code[5:].lower()}"
        status, _, headers = server.post("/pair", {"code": friendly})
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/")

    def test_five_wrong_codes_lock_that_address(self):
        devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        for _ in range(5):
            status, _, headers = server.post("/pair", {"code": "WRONGCODE1"})
            self.assertEqual(status, 303)
            self.assertIn("error=", headers["Location"])
        status, _, headers = server.post("/pair", {"code": "WRONGCODE1"})
        self.assertIn("too many wrong codes", urllib.parse.unquote(headers["Location"]))

    def test_the_device_cookie_is_not_in_the_database(self):
        device, code = devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        server.post("/pair", {"code": code})
        token = next(c.value for c in server.jar if c.name == "coontie_device")
        self.assertTrue(token)
        raw = self.db.read_bytes()
        self.assertNotIn(token.encode(), raw, "the token must exist only as a verifier")
        self.assertNotIn(code.encode(), raw, "and the code must not be left behind")

    def test_a_revoked_terminal_is_sent_back_to_pairing(self):
        device, code = devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        server.post("/pair", {"code": code})
        self.assertEqual(server.get("/")[0], 200)
        devices.revoke(self.ws, device.id, actor="Maria", at=NOW)
        status, _, headers = server.get("/", follow=False)
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/pair")

    def test_a_paired_terminal_still_cannot_post_from_a_foreign_origin(self):
        device, code = devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        server.post("/pair", {"code": code})
        server.get("/")
        token = server.httpd.RequestHandlerClass.app.token
        status, _, _ = server.post("/operator", {"operator": "Maria", "token": token},
                                   origin="http://evil.example")
        self.assertEqual(status, 403)

    def test_a_paired_terminal_can_post_from_its_own_origin(self):
        device, code = devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        server.post("/pair", {"code": code})
        server.get("/")  # a page load is what sets the session cookie
        token = server.httpd.RequestHandlerClass.app.token
        status, _, _ = server.post("/operator", {"operator": "Maria", "token": token},
                                   origin=f"http://127.0.0.1:{server.port}")
        self.assertEqual(status, 303)

    def test_pairing_and_revocation_are_on_the_ledger_and_hold_no_credential(self):
        device, code = devices.add_device(self.ws, "cure room tablet", actor="Maria", at=NOW)
        server = self.start()
        server.post("/pair", {"code": code})
        devices.revoke(self.ws, device.id, actor="Maria", at=NOW)
        paired = self.ws.ledger.latest("device_paired")
        revoked = self.ws.ledger.latest("device_revoked")
        self.assertEqual(paired.payload["device"], device.id)
        self.assertEqual(revoked.payload["device"], device.id)
        for entry in (paired, revoked):
            blob = str(entry.payload)
            self.assertNotIn(code, blob)
            self.assertNotIn("token", blob.lower())


class TestTheCommandLine(unittest.TestCase):
    """The flags have to reach the server: a --lan that silently serves loopback is a lie."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def run_cli(self, *args):
        import subprocess
        import os

        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        return subprocess.run([sys.executable, "-m", "coontie.cli", "--db", str(self.db), *args],
                              capture_output=True, text=True, env=env, timeout=60)

    def test_serve_lan_without_a_terminal_is_refused_by_the_command(self):
        result = self.run_cli("serve", "--lan", "--port", "8099")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no terminal is registered", result.stdout + result.stderr)

    def test_terminal_add_and_list_from_the_command_line(self):
        added = self.run_cli("terminal", "add", "--name", "cure room tablet")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertIn("pairing code:", added.stdout)
        listed = self.run_cli("terminal", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("cure room tablet", listed.stdout)


class TestTerminalCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_a_code_expires(self):
        device, code = devices.add_device(self.ws, "tablet", actor="Maria", at=NOW)
        with self.assertRaises(devices.DeviceError) as ctx:
            devices.pair(self.ws, code, at=NOW + devices.CODE_TTL + timedelta(seconds=1))
        self.assertIn("expired", str(ctx.exception))

    def test_a_device_needs_a_name(self):
        with self.assertRaises(devices.DeviceError):
            devices.add_device(self.ws, "  ", actor="Maria", at=NOW)

    def test_revoking_twice_says_when_it_was_revoked(self):
        device, _ = devices.add_device(self.ws, "tablet", actor="Maria", at=NOW)
        devices.revoke(self.ws, device.id, actor="Maria", at=NOW)
        with self.assertRaises(devices.DeviceError) as ctx:
            devices.revoke(self.ws, device.id, actor="Maria", at=NOW)
        self.assertIn("already revoked", str(ctx.exception))

    def test_the_limiter_forgets_old_failures(self):
        limiter = devices.Limiter()
        for _ in range(devices.MAX_ATTEMPTS):
            limiter.fail("10.0.0.9", now=NOW)
        self.assertGreater(limiter.retry_after("10.0.0.9", now=NOW), 0)
        self.assertEqual(limiter.retry_after("10.0.0.9", now=NOW + devices.LOCKOUT), 0)
        self.assertEqual(limiter.retry_after("10.0.0.8", now=NOW), 0)

    def test_a_token_belongs_to_one_terminal(self):
        first, code = devices.add_device(self.ws, "one", actor="Maria", at=NOW)
        second, code2 = devices.add_device(self.ws, "two", actor="Maria", at=NOW)
        _, token = devices.pair(self.ws, code, at=NOW)
        _, token2 = devices.pair(self.ws, code2, at=NOW)
        self.assertEqual(devices.by_token(self.ws, token).id, first.id)
        self.assertEqual(devices.by_token(self.ws, token2).id, second.id)
        self.assertIsNone(devices.by_token(self.ws, "not-a-token"))


if __name__ == "__main__":
    unittest.main()
