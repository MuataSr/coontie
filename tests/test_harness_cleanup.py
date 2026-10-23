"""A test harness that leaks a server on failure is a harness that lies about a quiet machine.

Unittest does not call `tearDown` when `setUp` raises, and `Appliance.__init__` raises while already
holding the child's handle, so every failing run of a gate module used to leave one `coontie serve`
listening on a scratch database. Twenty-five of them were found alive on the build machine, holding
1.1 GB. These tests are the proof that the two repaired paths stay repaired.
"""

import itertools
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import test_g1_gate as g1  # noqa: E402


class FakeProc:
    """Stands in for the child a failed start would otherwise orphan."""

    def __init__(self):
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return 0 if (self.terminated or self.killed) else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return 0


def port_is_open(port: int) -> bool:
    probe = socket.socket()
    probe.settimeout(0.5)
    try:
        return probe.connect_ex(("127.0.0.1", port)) == 0
    finally:
        probe.close()


class TestAStartThatNeverAnswers(unittest.TestCase):
    def test_the_child_is_stopped_before_the_error_is_raised(self):
        fake = FakeProc()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ws.sqlite3"
            with mock.patch.object(g1.subprocess, "Popen", return_value=fake), \
                 mock.patch.object(g1.urllib.request, "urlopen", side_effect=OSError("no server")), \
                 mock.patch.object(g1.time, "time", side_effect=itertools.count(0, 40)):
                with self.assertRaises(RuntimeError):
                    g1.Appliance(db)
        self.assertTrue(fake.terminated, "a start that never answers must not leave the child running")
        self.assertTrue(fake.waited, "and it must be reaped, not signalled and abandoned")


class TestASetupThatFails(unittest.TestCase):
    """The real path: a server that starts fine, then a setUp assertion that fails."""

    def run_one(self, inner):
        result = unittest.TestResult()
        inner("test_placeholder").run(result)
        self.assertEqual(len(result.errors) + len(result.failures), 1,
                         "the inner test was supposed to fail its setup")
        return result

    def build_inner(self, db, seen, *, cleanup):
        class Inner(unittest.TestCase):
            def setUp(self):
                self.app = g1.Appliance(db)
                seen.append(self.app)
                if cleanup:
                    # the line this increment added to all six gate modules
                    self.addCleanup(self.app.stop)
                self.fail("a setup that fails after the server is already running")

            def test_placeholder(self):
                self.assertTrue(True)

        return Inner

    def test_a_failing_setup_leaves_nothing_listening(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ws.sqlite3"
            g1.seed(db)
            self.run_one(self.build_inner(db, seen, cleanup=True))
            app = seen[0]
            self.assertIsNotNone(app.proc.poll(), "the child outlived a setup that failed")
            self.assertFalse(port_is_open(app.port), f"port {app.port} is still listening")

    def test_stop_is_idempotent_because_cleanup_and_teardown_both_call_it(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ws.sqlite3"
            g1.seed(db)
            app = g1.Appliance(db)
            try:
                app.stop()
                app.stop()  # tearDown runs after addCleanup; the second call must be a no-op
            finally:
                self.assertIsNotNone(app.proc.poll())
            self.assertFalse(port_is_open(app.port))


if __name__ == "__main__":
    unittest.main()
