"""Operators: from a claimed name to a person who signed in.

Ten assertions, one per promise in `docs/flows/operators.md`, against a real server on a real socket.
The regression that matters most is the first one: a facility that enrols nobody must see no change.
"""

import re
import sys
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_lan_gate import Server, free_port, seed  # noqa: E402

from coontie import people  # noqa: E402
from coontie.workspace import Workspace  # noqa: E402

NOW = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)
PASS = "grove-light-2026"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        self.maria = self.ws.add_employee(full_name="Maria Lopez", date_of_birth="1988-04-02",
                                          hire_date="2024-03-11", email="maria@example.com", at=NOW)
        self.ana = self.ws.add_employee(full_name="Ana Ruiz", date_of_birth="1990-01-05",
                                        hire_date="2025-02-01", email="ana@example.com", at=NOW)
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.close()
        self.ws.close()
        self.tmp.cleanup()

    def start(self):
        self.server = Server(self.db, lan=False)
        self.server.wait()
        return self.server

    def token_from_signin(self):
        status, body, _ = self.server.get("/signin")
        self.assertEqual(status, 200)
        match = re.search(r"name='token' value='([^']+)'", body)
        self.assertTrue(match, "the sign-in form must carry the session token")
        return match.group(1)

    def enrol(self, person=None):
        person = person or self.ana
        return self.ws.set_passphrase(person.id, PASS, actor="Maria Lopez", at=NOW)


class TestNobodyEnrolled(Base):
    """The regression: enrolment is opt-in, and its absence must be invisible."""

    def test_a_record_with_no_passphrase_serves_every_screen_and_says_the_name_is_a_claim(self):
        server = self.start()
        status, body, _ = server.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Today", body)
        self.assertIn('action="/operator"', body, "the name field is the honest fallback")
        self.assertNotIn("Sign out", body)

    def test_the_signin_page_explains_that_nobody_has_a_passphrase_yet(self):
        server = self.start()
        status, body, _ = server.get("/signin")
        self.assertEqual(status, 200)
        self.assertIn("Nobody has a passphrase yet", body)
        self.assertIn("coontie passphrase --id emp-… --set", body)
        self.assertNotIn("type='password'", body)


class TestTheGate(Base):
    def test_once_one_person_has_a_passphrase_only_the_way_in_answers(self):
        self.enrol()
        server = self.start()
        for path in ("/", "/inventory", "/audit", "/outbox", "/setup"):
            status, _, headers = server.get(path, follow=False)
            self.assertEqual(status, 303, path)
            self.assertEqual(headers["Location"], "/signin", path)
        self.assertEqual(server.get("/health", follow=False)[0], 200)

    def test_the_right_passphrase_signs_in_and_the_name_comes_from_the_session(self):
        self.enrol()
        server = self.start()
        token = self.token_from_signin()
        status, _, headers = server.post("/signin", {"token": token, "employee": self.ana.id,
                                                     "passphrase": PASS})
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/")
        status, body, _ = server.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Ana Ruiz", body)
        self.assertIn("Sign out", body)
        self.assertNotIn('action="/operator"', body, "a signed name is not a text box")

    def test_only_people_with_a_passphrase_are_offered(self):
        self.enrol()
        server = self.start()
        _, body, _ = server.get("/signin")
        self.assertIn("Ana Ruiz", body)
        self.assertNotIn("Maria Lopez", body)

    def test_a_forged_person_cookie_is_no_sign_in(self):
        self.enrol()
        server = self.start()
        import http.cookiejar

        cookie = http.cookiejar.Cookie(0, "coontie_person", f"{self.ana.id}.{'0' * 32}", None, False,
                                      "127.0.0.1", False, False, "/", True, False, None, True, None,
                                      None, {})
        server.jar.set_cookie(cookie)
        status, _, headers = server.get("/", follow=False)
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/signin")

    def test_a_wrong_passphrase_counts_down_and_five_lock_the_address(self):
        self.enrol()
        server = self.start()
        token = self.token_from_signin()
        for expected in (4, 3, 2, 1):
            status, _, headers = server.post("/signin", {"token": token, "employee": self.ana.id,
                                                         "passphrase": "not-the-one-1"})
            self.assertEqual(status, 303)
            self.assertIn(f"{expected} tries left", urllib.parse.unquote(headers["Location"]))
        server.post("/signin", {"token": token, "employee": self.ana.id,
                               "passphrase": "not-the-one-1"})
        status, _, headers = server.post("/signin", {"token": token, "employee": self.ana.id,
                                                    "passphrase": PASS})
        self.assertIn("too many wrong passphrases",
                      urllib.parse.unquote(headers["Location"]),
                      "the lockout must not care that the fifth guess was the right one")

    def test_signing_in_and_out_reach_the_ledger_with_the_employee_id(self):
        self.enrol()
        server = self.start()
        token = self.token_from_signin()
        server.post("/signin", {"token": token, "employee": self.ana.id, "passphrase": PASS})
        server.post("/signout", {"token": token})
        signed_in = self.ws.ledger.latest("person_signed_in")
        signed_out = self.ws.ledger.latest("person_signed_out")
        self.assertEqual(signed_in.payload["employee"], self.ana.id)
        self.assertEqual(signed_out.payload["employee"], self.ana.id)
        self.assertEqual(signed_in.payload["name"], "Ana Ruiz")
        self.assertEqual(server.get("/", follow=False)[0], 303, "signing out ends the session")

    def test_forget_returns_the_record_to_the_claimed_name(self):
        self.enrol()
        server = self.start()
        self.assertEqual(server.get("/", follow=False)[0], 303)
        self.ws.forget_passphrase(self.ana.id, actor="Maria Lopez", at=NOW)
        status, body, _ = server.get("/")
        self.assertEqual(status, 200)
        self.assertIn('action="/operator"', body)


class TestTheRecordItself(Base):
    def test_the_passphrase_is_nowhere_in_the_database_bytes(self):
        self.enrol()
        raw = self.db.read_bytes()
        self.assertNotIn(PASS.encode(), raw)
        row = self.ws.conn.execute("SELECT passphrase_verifier, passphrase_kdf FROM employees"
                                  " WHERE id = ?", (self.ana.id,)).fetchone()
        self.assertTrue(row["passphrase_verifier"].startswith("pbkdf2_sha256$300000$"))
        self.assertEqual(row["passphrase_kdf"], "pbkdf2_sha256")

    def test_the_ledger_names_the_employee_and_never_the_secret(self):
        self.enrol()
        entry = self.ws.ledger.latest("passphrase_set")
        self.assertEqual(entry.payload["employee"], self.ana.id)
        self.assertNotIn(PASS, str(entry.payload))
        self.assertIn("verifier", entry.payload["note"])

    def test_strength_refusals(self):
        cases = {
            "short-one": "shorter than",
            "ana-ruiz-passphrase": "contains the person's name",
            "aaaaaaaaaaaaaaaa": "one repeated character",
        }
        for value, expected in cases.items():
            with self.assertRaises(ValueError) as ctx:
                people.check_passphrase(value, name="Ana Ruiz")
            self.assertIn(expected, str(ctx.exception))

    def test_a_disabled_person_cannot_sign_in(self):
        self.enrol()
        self.ws.conn.execute("UPDATE employees SET active = 0 WHERE id = ?", (self.ana.id,))
        self.ws.conn.commit()
        with self.assertRaises(people.SignInError) as ctx:
            people.sign_in(self.ws, self.ana.id, PASS)
        self.assertIn("no longer active", str(ctx.exception))

    def test_signing_in_as_someone_without_a_passphrase_says_what_to_do(self):
        with self.assertRaises(people.SignInError) as ctx:
            people.sign_in(self.ws, self.maria.id, PASS)
        self.assertIn("no passphrase", str(ctx.exception))
        self.assertIn("coontie passphrase --id", str(ctx.exception))


class TestTheCommandLine(Base):
    def run_cli(self, *args):
        import os
        import subprocess

        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        return subprocess.run([sys.executable, "-m", "coontie.cli", "--db", str(self.db), *args],
                              capture_output=True, text=True, env=env, timeout=120)

    def test_set_verify_and_forget_through_the_real_command(self):
        set_result = self.run_cli("passphrase", "--id", self.ana.id, "--set", "--value", PASS,
                                  "--actor", "Maria Lopez")
        self.assertEqual(set_result.returncode, 0, set_result.stderr)
        self.assertIn("passphrase set", set_result.stdout)

        good = self.run_cli("passphrase", "--id", self.ana.id, "--verify", "--value", PASS)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("matches", good.stdout)

        bad = self.run_cli("passphrase", "--id", self.ana.id, "--verify", "--value", "another-guess-1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("does not match", bad.stdout)

        weak = self.run_cli("passphrase", "--id", self.ana.id, "--set", "--value", "ana")
        self.assertEqual(weak.returncode, 1)
        self.assertIn("refused", weak.stdout + weak.stderr)

        forget = self.run_cli("passphrase", "--id", self.ana.id, "--forget")
        self.assertEqual(forget.returncode, 0, forget.stderr)
        self.assertFalse(self.ws.employee(self.ana.id).can_sign_in)

    def test_an_unknown_employee_is_refused_by_name(self):
        result = self.run_cli("passphrase", "--id", "emp-nope", "--set", "--value", PASS)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no employee", result.stdout + result.stderr)


class TestTheLimiterItself(unittest.TestCase):
    def test_the_window_expires_and_other_keys_are_untouched(self):
        from coontie.attempts import Limiter

        limiter = Limiter()
        for _ in range(5):
            limiter.fail("10.0.0.9", now=NOW)
        self.assertGreater(limiter.retry_after("10.0.0.9", now=NOW), 0)
        self.assertEqual(limiter.remaining("10.0.0.9"), 0)
        self.assertEqual(limiter.retry_after("10.0.0.9", now=NOW + timedelta(minutes=16)), 0)
        self.assertEqual(limiter.retry_after("10.0.0.8", now=NOW), 0)


if __name__ == "__main__":
    unittest.main()
