"""The ledger is append-only, chain-verified, and exportable on demand."""

import unittest
from datetime import datetime, timedelta, timezone

from mmtc_record.store import GENESIS, Ledger

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def sample_ledger() -> Ledger:
    ledger = Ledger(":memory:")
    ledger.append(
        "seed_clone_batch",
        {"facility_location": "FL-1", "room": "G1", "cultivar": "Blue Dream", "count": 50},
        T0,
        facility_id="FL-1",
    )
    ledger.append(
        "immature_plant",
        {"facility_location": "FL-1", "room": "G1", "cultivar": "Blue Dream", "is_mother_plant": False},
        T0 + timedelta(days=14),
        facility_id="FL-1",
    )
    return ledger


class TestChain(unittest.TestCase):
    def test_first_entry_links_to_genesis(self):
        ledger = sample_ledger()
        first = ledger.entries()[0]
        self.assertEqual(first.prev_hash, GENESIS)

    def test_chain_verifies(self):
        self.assertEqual(sample_ledger().verify_chain(), (True, "ok"))

    def test_tampering_is_detected(self):
        ledger = sample_ledger()
        ledger.conn.execute("UPDATE events SET payload = ? WHERE seq = 1", ('{"count": 5000}',))
        ledger.conn.commit()
        ok, reason = ledger.verify_chain()
        self.assertFalse(ok)
        self.assertIn("seq 1", reason)

    def test_deleting_a_row_breaks_the_chain(self):
        ledger = sample_ledger()
        ledger.conn.execute("DELETE FROM events WHERE seq = 1")
        ledger.conn.commit()
        ok, _ = ledger.verify_chain()
        self.assertFalse(ok)


class TestReadsAndExport(unittest.TestCase):
    def test_query_by_event_key(self):
        ledger = sample_ledger()
        self.assertEqual(len(ledger.entries("seed_clone_batch")), 1)
        self.assertEqual(len(ledger.entries()), 2)

    def test_csv_export_carries_the_dept_columns(self):
        ledger = sample_ledger()
        csv_text = ledger.export_csv()
        header = csv_text.splitlines()[0]
        for col in ("seq", "event_key", "occurred_at", "recorded_at", "facility_id", "prev_hash", "hash"):
            self.assertIn(col, header)
        self.assertIn("Blue Dream", csv_text)
        self.assertEqual(len(csv_text.splitlines()), 3)  # header + 2 records


if __name__ == "__main__":
    unittest.main()
