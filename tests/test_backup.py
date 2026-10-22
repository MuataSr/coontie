"""A backup is a control only if it restores, and only if it notices when it has been altered.

These tests do the three things an operator needs proven: the copy is the same record, an altered
copy is refused, and a restore lands on the record with proof that it was the same record.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from coontie import backup as backups
from coontie.workspace import Workspace

sys.path.insert(0, str(Path(__file__).parent))
import test_g4_gate as g4  # noqa: E402  (a seeded facility, a dispatched manifest, a real artifact)


def seed(db: Path) -> None:
    """A facility with a dispatched manifest, plus one artifact in the record's reports directory."""
    g4.seed(db)
    reports = db.resolve().parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "outage-out-1b2c.csv").write_text("inventory id,reason\nFL-INV-001,miscount\n",
                                                 encoding="utf-8")


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_the_copy_is_the_same_record_and_the_manifest_proves_it(self):
        saved = backups.backup(self.ws, self.root / "backups")
        self.assertTrue(saved.database.exists())
        ok, problems, manifest = backups.verify(saved.manifest)
        self.assertTrue(ok, problems)
        live = backups._read_state(self.db)
        self.assertEqual(manifest["events"], live["events"])
        self.assertEqual(manifest["chain_head"], live["chain_head"])
        self.assertEqual(manifest["facility"], "Nature's Grace FL, LLC")
        self.assertTrue(manifest["license"].startswith("MMTC-"))

    def test_the_name_carries_the_head_and_the_count_so_two_files_can_be_compared(self):
        saved = backups.backup(self.ws, self.root / "backups")
        state = backups._read_state(self.db)
        self.assertIn(state["chain_head"][:8], saved.database.name)
        self.assertTrue(saved.database.name.endswith(f"-{state['events']}.sqlite3"))

    def test_every_report_file_is_copied_and_hashed(self):
        saved = backups.backup(self.ws, self.root / "backups")
        _, _, manifest = backups.verify(saved.manifest)
        self.assertEqual([r["name"] for r in manifest["reports"]], ["outage-out-1b2c.csv"])
        for entry in manifest["reports"]:
            copied = saved.directory / "reports" / entry["name"]
            self.assertTrue(copied.exists(), entry["name"])
            self.assertEqual(backups._sha256(copied), entry["sha256"])

    def test_the_backup_is_an_instant_not_a_torn_file(self):
        saved = backups.backup(self.ws, self.root / "backups")
        at_backup = json.loads(saved.manifest.read_text())["events"]
        self.ws.ledger.append("note", {"body": "written after the backup"},
                              datetime.now(timezone.utc))
        after = backups._read_state(saved.database)["events"]
        self.assertEqual(after, at_backup, "the copy changed when the live record did")
        self.assertGreater(backups._read_state(self.db)["events"], at_backup)

    def test_a_backup_needs_room_for_itself(self):
        with self.assertRaises(backups.BackupError) as ctx:
            backups.backup(self.ws, self.root / "backups", free_bytes=1024)
        self.assertIn("nothing was written", str(ctx.exception))
        self.assertFalse(list((self.root / "backups").glob("*.sqlite3")))


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        self.saved = backups.backup(self.ws, self.root / "backups")

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_a_flipped_byte_in_the_database_is_refused(self):
        data = bytearray(self.saved.database.read_bytes())
        data[len(data) // 2] = (data[len(data) // 2] + 1) % 256
        self.saved.database.write_bytes(bytes(data))
        ok, problems, _ = backups.verify(self.saved.manifest)
        self.assertFalse(ok)
        self.assertTrue(any("does not hash" in p for p in problems), problems)

    def test_a_truncated_database_is_refused(self):
        self.saved.database.write_bytes(self.saved.database.read_bytes()[:4096])
        ok, problems, _ = backups.verify(self.saved.manifest)
        self.assertFalse(ok)
        self.assertTrue(any("bytes" in p for p in problems), problems)

    def test_a_missing_report_is_refused(self):
        _, _, manifest = backups.verify(self.saved.manifest)
        victim = self.saved.directory / "reports" / manifest["reports"][0]["name"]
        victim.unlink()
        ok, problems, _ = backups.verify(self.saved.manifest)
        self.assertFalse(ok)
        self.assertTrue(any("missing" in p for p in problems), problems)

    def test_a_database_with_no_manifest_beside_it_is_not_a_backup(self):
        orphan = self.root / "orphan.sqlite3"
        orphan.write_bytes(self.saved.database.read_bytes())
        with self.assertRaises(backups.BackupError) as ctx:
            backups.verify(orphan)
        self.assertIn("not a backup", str(ctx.exception))

    def test_the_directory_that_holds_one_is_enough(self):
        ok, problems, manifest = backups.verify(self.saved.directory)
        self.assertTrue(ok, problems)
        self.assertEqual(manifest["format"], backups.FORMAT)


class TestRestore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        self.saved = backups.backup(self.ws, self.root / "backups")
        self.live_head = self.saved.chain_head

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_a_restore_brings_back_every_table(self):
        target = self.root / "restored.sqlite3"
        result = backups.restore(self.saved.manifest, target, actor="Maria Lopez")
        self.assertEqual(result["events"], self.saved.events)
        live, restored = backups._counts(self.db), backups._counts(target)
        for table, count in live.items():
            if table == "events":
                self.assertEqual(restored[table], count + 1, "only the restore event is new")
            else:
                self.assertEqual(restored[table], count, table)
        ws = Workspace(target)
        try:
            ok, summary = ws.verify()
            self.assertTrue(ok, summary)
        finally:
            ws.close()

    def test_the_restore_is_on_the_record_with_both_heads_and_who_ran_it(self):
        target = self.root / "restored.sqlite3"
        backups.restore(self.saved.manifest, target, actor="Maria Lopez")
        ws = Workspace(target)
        try:
            entry = ws.ledger.latest("restore_performed")
            assert entry is not None, "the restore was not recorded"
            self.assertEqual(entry.payload["backup_chain_head"], self.live_head)
            self.assertEqual(entry.payload["restored_chain_head"], self.live_head)
            self.assertEqual(entry.payload["actor"], "Maria Lopez")
            self.assertEqual(entry.payload["backup"], self.saved.database.name)
        finally:
            ws.close()

    def test_the_restore_event_is_appended_only_after_the_file_proves_itself(self):
        # a backup whose copied file was altered must not reach the append
        data = bytearray(self.saved.database.read_bytes())
        data[len(data) // 2] = (data[len(data) // 2] + 1) % 256
        self.saved.database.write_bytes(bytes(data))
        target = self.root / "never.sqlite3"
        with self.assertRaises(backups.BackupError):
            backups.restore(self.saved.manifest, target)
        self.assertFalse(target.exists())

    def test_an_existing_record_is_not_overwritten_without_force(self):
        with self.assertRaises(backups.BackupError) as ctx:
            backups.restore(self.saved.manifest, self.db)
        self.assertIn("--force", str(ctx.exception))
        # and with force it lands, recording what it replaced
        result = backups.restore(self.saved.manifest, self.db, force=True, actor="Maria Lopez")
        self.assertEqual(result["after"]["events"], self.saved.events + 1)

    def test_artifacts_already_in_the_target_are_not_deleted(self):
        target = self.root / "restored.sqlite3"
        keep = self.root / "reports" / "invoice-inv-999.txt"
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text("an artifact the target already had\n")
        backups.restore(self.saved.manifest, target, force=True, actor="Maria Lopez")
        self.assertTrue(keep.exists())


class TestPrune(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "ws.sqlite3"
        seed(self.db)
        self.ws = Workspace(self.db)
        self.dir = self.root / "backups"
        self.saved = []
        for hour in range(4):
            at = datetime(2026, 10, 22, 6 + hour, tzinfo=timezone.utc)
            self.saved.append(backups.backup(self.ws, self.dir, at=at))
            self.ws.ledger.append("note", {"body": f"hour {hour}"},
                                  datetime(2026, 10, 22, 6 + hour, tzinfo=timezone.utc))

    def tearDown(self):
        self.ws.close()
        self.tmp.cleanup()

    def test_pruning_keeps_the_newest_and_removes_the_oldest(self):
        removed = backups.prune(self.dir, keep=2)
        self.assertEqual(len(removed), 2)
        left = sorted(p.name for p in self.dir.glob("*.sqlite3"))
        self.assertEqual(left, sorted(b.database.name for b in self.saved[-2:]))
        self.assertTrue(self.saved[-1].database.exists())

    def test_a_keep_of_zero_is_refused(self):
        with self.assertRaises(backups.BackupError):
            backups.prune(self.dir, keep=0)

    def test_a_backup_that_does_not_verify_is_not_pruned(self):
        victim = self.saved[0].database
        victim.write_bytes(victim.read_bytes()[:2048])
        with self.assertRaises(backups.BackupError) as ctx:
            backups.prune(self.dir, keep=2)
        self.assertIn("verify", str(ctx.exception))
        self.assertTrue(victim.exists(), "an unverified backup is kept for a person to decide")


class TestTheSetupScreen(unittest.TestCase):
    def test_the_form_copies_the_record_and_the_page_names_the_copy(self):
        from coontie import web

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            db = root / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                note = web.apply_setup_form(ws, "backup", {}, "Maria Lopez")
                self.assertIn("Copied", note)
                page = web.App(db).render_setup(ws, "Maria Lopez")
            finally:
                ws.close()
            self.assertIn("Copies in", page)
            # two copies in the same minute must still be told apart, by the token --from takes
            self.assertRegex(page, r"<td class='ident' title='coontie-backup-\d{8}T\d{6}Z-")
            self.assertIn("Verified", page)
            self.assertIn("EDT", page)  # the operator's clock, not the manifest's UTC
            self.assertIn("A restore is never a button", page)
            self.assertEqual(len(list((root / "backups").glob("*.sqlite3"))), 1)

    def test_a_copy_that_does_not_verify_is_named_rather_than_deleted(self):
        from coontie import web

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            db = root / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                web.apply_setup_form(ws, "backup", {}, "Maria Lopez")
                copied = next((root / "backups").glob("*.sqlite3"))
                copied.write_bytes(copied.read_bytes()[:2048])
                page = web.App(db).render_setup(ws, "Maria Lopez")
            finally:
                ws.close()
            self.assertIn("Does not verify", page)
            self.assertTrue(copied.exists())


class TestDrill(unittest.TestCase):
    def test_the_drill_proves_a_restore_and_catches_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            db = root / "ws.sqlite3"
            seed(db)
            steps = backups.drill(db, into=root / "drill")
            text = "\n".join(steps)
            self.assertIn("backed up", text)
            self.assertIn("every table matches", text)
            self.assertIn("a flipped byte is caught", text)
            self.assertIn("a truncated file is caught", text)
            self.assertIn("drill passed", text)

    def test_the_restore_survives_the_drill_onto_the_live_record(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            db = root / "ws.sqlite3"
            seed(db)
            backups.drill(db, into=root / "drill")
            ws = Workspace(db)
            try:
                ok, summary = ws.verify()
                self.assertTrue(ok, summary)
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()
