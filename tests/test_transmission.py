"""The outbox: what is waiting, what was sealed, and what "handed over" is allowed to mean.

The point of these tests is the honesty boundary. A package is a file. A folder hand-off is a
hand-off. Nothing in this build may say a record was delivered, and the tests say so in the words a
user would read.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from coontie import transmission as tx
from coontie.workspace import Workspace

sys.path.insert(0, str(Path(__file__).parent))
import test_g4_gate as g4  # noqa: E402  (a seeded facility with catalogue events in the ledger)

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def seed(db: Path) -> None:
    g4.seed(db)


class TestWindows(unittest.TestCase):
    def test_a_realtime_record_is_due_when_it_is_made(self):
        self.assertEqual(tx.window_for("dispensation"), timedelta(0))
        self.assertEqual(tx.window_for("transfer_out"), timedelta(0))

    def test_an_ordinary_record_gets_the_twelve_hour_window(self):
        self.assertEqual(tx.window_for("inventory_lot_create"), timedelta(hours=12))
        self.assertEqual(tx.window_for("harvest"), timedelta(hours=12))

    def test_a_key_outside_the_catalogue_falls_back_to_the_default_window(self):
        self.assertEqual(tx.window_for("appearance_chosen"), timedelta(hours=12))


class TestQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_only_catalogue_events_are_owed(self):
        waiting = tx.owed(self.ws, now=NOW)
        self.assertTrue(waiting)
        keys = {item.event for item in waiting}
        self.assertIn("inventory_lot_create", keys)
        self.assertNotIn("appearance_chosen", keys)  # a Coontie key owes nothing to DH5059

    def test_the_queue_is_oldest_first(self):
        waiting = tx.owed(self.ws, now=NOW)
        times = [item.occurred_at for item in waiting]
        self.assertEqual(times, sorted(times), "a queue that opens on the newest row hides what is late")

    def test_overdue_is_decided_by_the_catalogue_window(self):
        waiting = tx.owed(self.ws, now=NOW)
        first = waiting[0]
        self.assertTrue(first.overdue(first.due_at))
        self.assertTrue(first.overdue(first.due_at + timedelta(minutes=1)))
        self.assertFalse(first.overdue(first.due_at - timedelta(seconds=1)))

    def test_the_backlog_counts_what_is_late_separately(self):
        state = tx.backlog(self.ws, now=NOW)
        self.assertEqual(state["waiting"], len(tx.owed(self.ws, now=NOW)))
        self.assertGreaterEqual(state["overdue"], 0)
        self.assertLessEqual(state["overdue"], state["waiting"])
        self.assertFalse(state["any_handed_over"])


class TestPackages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_a_package_holds_the_waiting_records_and_hashes_to_its_contents(self):
        wanted = min(4, len(tx.owed(self.ws, now=NOW)))
        pack = tx.package(self.ws, at=NOW, limit=4)
        self.assertTrue(pack.path.exists())
        body = json.loads(pack.path.read_text())
        self.assertEqual(body["format"], tx.FORMAT)
        self.assertEqual(body["events"], wanted)
        self.assertEqual(pack.events, wanted)
        self.assertEqual(body["first_seq"], pack.first_seq)
        recomputed = hashlib.sha256(json.dumps(
            {k: v for k, v in body.items() if k != "sha256"}, sort_keys=True).encode()).hexdigest()
        self.assertEqual(recomputed, body["sha256"])
        self.assertEqual(body["sha256"], pack.sha256)
        self.assertEqual(len(body["events_detail"]), wanted)

    def test_packaging_is_on_the_record(self):
        pack = tx.package(self.ws, at=NOW, limit=3)
        entry = self.ws.ledger.latest("transmission_packaged")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.payload["envelope"], pack.path.name)
        self.assertEqual(entry.payload["events"], 3)
        self.assertEqual(entry.payload["sha256"], pack.sha256)

    def test_the_packaged_records_leave_the_queue_before_they_are_handed_over(self):
        before = len(tx.owed(self.ws, now=NOW))
        tx.package(self.ws, at=NOW, limit=3)
        self.assertEqual(len(tx.owed(self.ws, now=NOW)), before - 3)

    def test_an_empty_queue_is_not_sealed_into_an_empty_envelope(self):
        tx.package(self.ws, at=NOW)  # everything
        with self.assertRaises(tx.OutboxError) as ctx:
            tx.package(self.ws, at=NOW)
        self.assertIn("nothing is waiting", str(ctx.exception))

    def test_an_unknown_adapter_name_is_refused_with_the_real_names(self):
        with self.assertRaises(tx.OutboxError) as ctx:
            tx.package(self.ws, at=NOW, adapter="biotrack")
        self.assertIn("stub", str(ctx.exception))
        self.assertIn("folder", str(ctx.exception))


class TestHandOver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        self.pack = tx.package(self.ws, at=NOW, limit=3)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_the_default_adapter_refuses_and_the_records_stay_owed(self):
        before = len(tx.owed(self.ws, now=NOW))
        result = tx.hand_over(self.ws, self.pack.id, adapter=tx.StubAdapter(), at=NOW)
        self.assertEqual(result.state, tx.FAILED)
        self.assertIn("nothing was sent", result.result)
        self.assertEqual(len(tx.owed(self.ws, now=NOW)), before + 3,
                         "a refused hand-off must put the records back in the queue")

    def test_a_folder_hand_off_copies_the_file_and_claims_no_delivery(self):
        folder = self.root / "handover"
        folder.mkdir()
        result = tx.hand_over(self.ws, self.pack.id, adapter=tx.FolderAdapter(folder), at=NOW)
        self.assertEqual(result.state, tx.HANDED_OVER)
        self.assertIn("delivery is not confirmed", result.result)
        self.assertTrue(Path(result.reference).exists())
        self.assertEqual(Path(result.reference).read_bytes(), self.pack.path.read_bytes())
        self.assertNotIn("delivered", result.result.lower())

    def test_the_hand_off_is_on_the_record_with_the_adapter_and_the_range(self):
        tx.hand_over(self.ws, self.pack.id, adapter=tx.StubAdapter(), at=NOW)
        entry = self.ws.ledger.latest("transmission_attempted")
        self.assertIsNotNone(entry)
        self.assertFalse(entry.payload["accepted"])
        self.assertEqual(entry.payload["adapter"], "stub")
        self.assertEqual(entry.payload["first_seq"], self.pack.first_seq)
        self.assertEqual(entry.payload["last_seq"], self.pack.last_seq)

    def test_one_hand_off_per_package(self):
        folder = self.root / "handover"
        folder.mkdir()
        tx.hand_over(self.ws, self.pack.id, adapter=tx.FolderAdapter(folder), at=NOW)
        with self.assertRaises(tx.OutboxError) as ctx:
            tx.hand_over(self.ws, self.pack.id, adapter=tx.FolderAdapter(folder), at=NOW)
        self.assertIn("one hand-off per package", str(ctx.exception))

    def test_a_package_whose_file_changed_is_refused(self):
        data = bytearray(self.pack.path.read_bytes())
        data[len(data) // 2] = (data[len(data) // 2] + 1) % 256
        self.pack.path.write_bytes(bytes(data))
        folder = self.root / "handover"
        folder.mkdir()
        with self.assertRaises(tx.OutboxError) as ctx:
            tx.hand_over(self.ws, self.pack.id, adapter=tx.FolderAdapter(folder), at=NOW)
        self.assertIn("no longer matches the hash", str(ctx.exception))

    def test_a_package_that_is_gone_cannot_be_handed_over(self):
        self.pack.path.unlink()
        with self.assertRaises(tx.OutboxError) as ctx:
            tx.hand_over(self.ws, self.pack.id, adapter=tx.StubAdapter(), at=NOW)
        self.assertIn("gone", str(ctx.exception))

    def test_a_folder_adapter_without_a_folder_is_refused(self):
        with self.assertRaises(tx.OutboxError) as ctx:
            tx.adapter_for("folder")
        self.assertIn("--to", str(ctx.exception))

    def test_a_folder_that_does_not_exist_fails_rather_than_pretending(self):
        result = tx.hand_over(self.ws, self.pack.id,
                              adapter=tx.FolderAdapter(self.root / "nope"), at=NOW)
        self.assertEqual(result.state, tx.FAILED)
        self.assertIn("not a directory", result.result)


class TestAbandon(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        self.pack = tx.package(self.ws, at=NOW, limit=2)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_withdrawing_needs_a_reason_and_returns_the_records(self):
        with self.assertRaises(tx.OutboxError):
            tx.abandon(self.ws, self.pack.id, reason="  ")
        before = len(tx.owed(self.ws, now=NOW))
        pack = tx.abandon(self.ws, self.pack.id, reason="sealed against the wrong facility", at=NOW)
        self.assertEqual(pack.state, tx.ABANDONED)
        self.assertTrue(self.pack.path.exists(), "the file stays on disk; only its state changes")
        self.assertEqual(len(tx.owed(self.ws, now=NOW)), before + 2)
        entry = self.ws.ledger.latest("transmission_abandoned")
        self.assertEqual(entry.payload["reason"], "sealed against the wrong facility")

    def test_a_handed_over_package_cannot_be_withdrawn(self):
        folder = self.root / "handover"
        folder.mkdir()
        tx.hand_over(self.ws, self.pack.id, adapter=tx.FolderAdapter(folder), at=NOW)
        with self.assertRaises(tx.OutboxError) as ctx:
            tx.abandon(self.ws, self.pack.id, reason="changed my mind", at=NOW)
        self.assertIn("handed_over", str(ctx.exception))


class TestTheScreen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        from coontie.web import App

        self.app = App(self.db)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_today_says_how_many_are_waiting_and_what_the_window_is(self):
        text = self.app.render_today(self.ws, "Maria Lopez")
        self.assertIn("not yet sent", text)
        self.assertIn("12 hours", text)
        self.assertIn("/outbox", text)

    def test_each_row_in_the_queue_names_which_record_it_is(self):
        page = self.app.render_outbox(self.ws, "Maria Lopez")
        self.assertIn("Which record", page)
        # four identical titles must still be four distinguishable rows
        self.assertRegex(page, r"<td class='ident'>(PL-\d+|stk-[0-9a-f]+|man-[0-9a-f]+|#\d+)</td>")

    def test_the_outbox_screen_states_the_limits_in_words(self):
        from coontie import web

        page = self.app.render_outbox(self.ws, "Maria Lopez")
        self.assertIn("What has not reached the department", page)
        self.assertIn("no department adapter", page)
        self.assertIn("never reports a record as delivered", page)
        # a package can be sealed from the screen, and the screen says what that is
        note = web.apply_outbox_form(self.ws, "package", {"package__adapter": "stub"}, "Maria Lopez")
        self.assertIn("Nothing was sent", note)
        page = self.app.render_outbox(self.ws, "Maria Lopez")
        self.assertIn("sealed, not handed over", page)

    def test_the_screen_reports_a_folder_hand_off_without_claiming_delivery(self):
        from coontie import web

        folder = self.root / "handover"
        folder.mkdir()
        note = web.apply_outbox_form(self.ws, "package", {"package__adapter": "folder"}, "Maria Lopez")
        self.assertIn("Sealed", note)
        pack_id = next(p.id for p in tx.packages(self.ws))
        note = web.apply_outbox_form(self.ws, "send", {
            "send__package": pack_id, "send__adapter": "folder", "send__to": str(folder)},
            "Maria Lopez")
        self.assertIn("handed over", note)
        self.assertIn("not delivered", note)


if __name__ == "__main__":
    unittest.main()
