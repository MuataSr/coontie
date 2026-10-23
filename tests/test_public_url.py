"""A tunnel address, named by the operator, widens the boundary by exactly one host.

The appliance refuses a request whose `Host` or `Origin` it does not recognise, which is what stops a
page in the operator's browser from writing to the record. A tunnel puts a stranger's hostname on every
request, so serving one requires an explicit `--public-url`: the address is typed by a person, never
guessed from the `Host` header, because "trust whatever arrives" is the check deleting itself.

These tests drive a real socket and assert both halves: the named address works, and every other
address is still refused.
"""

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from coontie import web  # noqa: E402
from coontie.workspace import Facility, Room, Workspace  # noqa: E402

TUNNEL = "https://kind-pine-1234.trycloudflare.com"


class Server:
    """A loopback server with a named public address in front of it."""

    def __init__(self, db: Path, *, public_url: str):
        self.httpd = web.serve(db, port=0, public_url=public_url)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def request(self, path: str, *, host: str, origin: str | None = None, body: str | None = None,
                cookie: str = "") -> tuple[int, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host}
        if origin:
            headers["Origin"] = origin
        if cookie:
            headers["Cookie"] = cookie
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            connection.request("POST" if body is not None else "GET", path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read().decode()
        finally:
            connection.close()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class TestTheNamedAddress(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        ws = Workspace(self.db)
        ws.add_facility(Facility(id="f1", name="Sand Pine Cultivation, LLC",
                                 license_number="MMTC-2026-0031", street="1100 Grove Road",
                                 city="Brooksville", state="FL", zip="34601"))
        ws.add_room(Room(id="g1", facility_id="f1", kind="grow", name="G1", number="01"))
        ws.close()
        self.server = Server(self.db, public_url=TUNNEL)

    def tearDown(self):
        self.server.close()
        self.tmp.cleanup()

    def test_the_tunnel_hostname_reaches_the_page(self):
        status, body = self.server.request("/", host="kind-pine-1234.trycloudflare.com")
        self.assertEqual(status, 200, body[:300])
        self.assertIn("Sand Pine Cultivation", body)

    def test_the_tunnel_origin_may_post_with_the_session_token(self):
        _, first = self.server.request("/", host="kind-pine-1234.trycloudflare.com")
        self.assertIn("Sand Pine Cultivation", first)
        app = self.server.httpd.RequestHandlerClass.app
        cookie = f"coontie_session={app.token}"
        status, body = self.server.request(
            "/operator", host="kind-pine-1234.trycloudflare.com", origin=TUNNEL,
            cookie=cookie, body=f"token={app.token}&operator=Muata+Kamdibe")
        self.assertIn(status, (200, 303), body[:300])

    def test_another_hostname_is_still_refused(self):
        status, body = self.server.request("/", host="attacker.example.com")
        self.assertEqual(status, 403, "a named address must widen by one host, not open the door")

    def test_another_origin_is_still_refused(self):
        app = self.server.httpd.RequestHandlerClass.app
        status, body = self.server.request(
            "/operator", host="kind-pine-1234.trycloudflare.com", origin="https://attacker.example.com",
            cookie=f"coontie_session={app.token}", body=f"token={app.token}&operator=Someone")
        self.assertEqual(status, 403, body[:200])

    def test_without_the_flag_the_tunnel_hostname_is_refused(self):
        plain = Server(self.db, public_url="")
        try:
            status, _ = plain.request("/", host="kind-pine-1234.trycloudflare.com")
            self.assertEqual(status, 403, "the boundary closes again when no address is named")
        finally:
            plain.close()


class TestTheRefusalSaysWhichAddress(unittest.TestCase):
    """A 403 with no address in it is a dead end for the operator holding the browser."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        ws = Workspace(self.db)
        ws.add_facility(Facility(id="f1", name="Sand Pine Cultivation, LLC",
                                 license_number="MMTC-2026-0031", street="1 Grove Road",
                                 city="Brooksville", state="FL", zip="34601"))
        ws.close()
        self.server = Server(self.db, public_url=TUNNEL)

    def tearDown(self):
        self.server.close()
        self.tmp.cleanup()

    def test_a_refused_post_names_the_origin_it_arrived_from(self):
        status, body = self.server.request(
            "/operator", host="proxy.example.com", origin="https://proxy.example.com",
            body="operator=Someone")
        self.assertEqual(status, 403)
        self.assertIn("proxy.example.com", body, "the page must name the address it refused")
        self.assertIn("--public-url", body, "and say which flag widens the record to it")

    def test_a_refused_host_is_named_even_with_no_origin(self):
        status, body = self.server.request("/operator", host="proxy.example.com", body="operator=X")
        self.assertEqual(status, 403)
        self.assertIn("proxy.example.com", body)


class TestAnOpaqueOrigin(unittest.TestCase):
    """A phone's in-app browser posts `Origin: null`; a hostile sandboxed frame posts the same thing.

    They cannot be told apart by the header, so the header stops being the gate and the session token
    is: it is unreadable cross-origin and the cookie is SameSite=Strict.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        ws = Workspace(self.db)
        ws.add_facility(Facility(id="f1", name="Sand Pine Cultivation, LLC",
                                 license_number="MMTC-2026-0031", street="1 Grove Road",
                                 city="Brooksville", state="FL", zip="34601"))
        ws.close()
        self.server = Server(self.db, public_url=TUNNEL)
        self.app = self.server.httpd.RequestHandlerClass.app

    def tearDown(self):
        self.server.close()
        self.tmp.cleanup()

    def test_a_null_origin_with_the_token_is_accepted(self):
        status, body = self.server.request(
            "/operator", host="kind-pine-1234.trycloudflare.com", origin="null",
            cookie=f"coontie_session={self.app.token}",
            body=f"token={self.app.token}&operator=Muata+Kamdibe")
        self.assertIn(status, (200, 303), body[:300])

    def test_a_null_origin_without_the_token_is_still_refused(self):
        status, body = self.server.request(
            "/operator", host="kind-pine-1234.trycloudflare.com", origin="null",
            cookie=f"coontie_session={self.app.token}", body="operator=Someone")
        self.assertIn(status, (403, 400), body[:300])
        self.assertNotIn("operator saved", body.lower())

    def test_a_foreign_origin_with_the_token_is_refused(self):
        status, _ = self.server.request(
            "/operator", host="kind-pine-1234.trycloudflare.com", origin="https://evil.example",
            cookie=f"coontie_session={self.app.token}",
            body=f"token={self.app.token}&operator=Someone")
        self.assertEqual(status, 403, "a real cross-site origin must stay refused")


class TestTheAddressIsCheckedNotTrusted(unittest.TestCase):
    def test_a_url_with_a_scheme_and_host_normalises(self):
        self.assertEqual(web.normalise_public_url("https://X.TryCloudflare.com/"), "https://x.trycloudflare.com")

    def test_a_url_with_a_path_is_refused(self):
        with self.assertRaises(SystemExit):
            web.normalise_public_url("https://example.com/record")

    def test_a_url_without_a_scheme_is_refused(self):
        with self.assertRaises(SystemExit):
            web.normalise_public_url("example.trycloudflare.com")

    def test_a_scheme_that_is_not_http_is_refused(self):
        with self.assertRaises(SystemExit):
            web.normalise_public_url("ftp://example.com")

    def test_no_url_means_no_widening(self):
        self.assertEqual(web.normalise_public_url(""), "")


if __name__ == "__main__":
    unittest.main()
