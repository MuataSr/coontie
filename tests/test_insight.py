"""Insight: lineage, explanation, prefill, anomalies, and a brief that reads like English."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from coontie.insight import anomalies, brief, explain, lineage, prefill, prefill_command
from coontie.workspace import Facility, Room, Workspace

T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def workspace(root: Path) -> Workspace:
    ws = Workspace(root / "ws.sqlite3")
    ws.add_facility(Facility(id="f1", name="Nature's Grace", license_number="MMTC-30",
                             street="1200 Grove Rd", city="Brooksville", state="FL", zip="34601"))
    ws.add_room(Room(id="inv1", facility_id="f1", kind="inventory", name="INV1", number="01"))
    ws.add_room(Room(id="inv2", facility_id="f1", kind="inventory", name="INV2", number="02"))
    return ws


class TestLineage(unittest.TestCase):
    def test_a_lot_traces_back_through_its_moves_and_forward_to_its_paperwork(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            lot = ws.new_lot(kind="cured and dried flower", cultivar="Blue Dream", weight="600",
                             room="inv1", at=T0)
            child = ws.split_lot(lot.id, amount="200", to_room="inv2", at=T0)
            ws.lab_sample(lot.id, weight="5", cmtl_id="ACS Laboratory", at=T0)
            lines = [line.render() for line in lineage(ws, lot.id)]
            text = "\n".join(lines)
            self.assertIn("Processing lot", text)
            self.assertIn("split: 200", text)
            self.assertIn("remaining 395", text)  # 600 - 200 split - 5 sample
            self.assertIn("lab sample 5", text)
            self.assertIn(child.id, text)
            ws.close()

    def test_an_unknown_reference_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            with self.assertRaises(ValueError):
                lineage(ws, "stk-nope")
            ws.close()


class TestExplanation(unittest.TestCase):
    def test_a_matching_move_is_marked(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            lot = ws.new_lot(kind="extract", cultivar="X", weight="600", room="inv1", at=T0)
            ws.split_lot(lot.id, amount="200", to_room="inv2", at=T0)
            candidates = explain(ws, lot.id, gap="200")
            self.assertEqual(sum(1 for c in candidates if c.matches), 1)
            self.assertTrue(any("MATCH" in c.line() for c in candidates))
            ws.close()

    def test_no_match_is_reported_as_no_match(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            lot = ws.new_lot(kind="extract", cultivar="X", weight="600", room="inv1", at=T0)
            ws.split_lot(lot.id, amount="200", to_room="inv2", at=T0)
            self.assertEqual([c for c in explain(ws, lot.id, gap="37") if c.matches], [])
            ws.close()


class TestPrefill(unittest.TestCase):
    def test_defaults_come_from_the_recipients_last_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            lot = ws.new_lot(kind="cured and dried flower", cultivar="Blue Dream", weight="500",
                             room="inv1", at=T0)
            vehicle = ws.register_vehicle(name="Van", plate="FL-1", make="Ford", model="Transit")
            ws.build_manifest(recipient_name="Tampa Dispensary", recipient_address="900 N Tampa St",
                              vehicle=vehicle.id, employee_ids=("Maria Lopez", "Dev Patel"),
                              departure_at=T0, arrival_at=T0 + timedelta(hours=3),
                              items=[(lot.id, "200", "")], route="I-75 south", at=T0)
            got = prefill(ws, "tampa")
            self.assertEqual(got["recipient_name"], "Tampa Dispensary")
            self.assertEqual(got["employees"], ["Maria Lopez", "Dev Patel"])
            self.assertIn("--item", prefill_command(ws, "tampa"))
            ws.close()

    def test_no_manifests_means_no_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            self.assertEqual(prefill(ws, "tampa"), {})
            self.assertEqual(prefill_command(ws, "tampa"), "")
            ws.close()


class TestAnomalies(unittest.TestCase):
    def test_a_short_history_gets_silence_not_a_guess(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            for i in range(3):
                ws.new_lot(kind="extract", cultivar="X", weight=str(100 + i), room="inv1",
                           at=T0 + timedelta(days=i))
            self.assertEqual(anomalies(ws), [])
            ws.close()

    def test_an_outlier_in_five_records_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            for i, weight in enumerate(["100", "102", "98", "101", "900"]):
                ws.new_lot(kind="extract", cultivar="X", weight=weight, room="inv1",
                           at=T0 + timedelta(days=i))
            found = anomalies(ws)
            self.assertTrue(found)
            self.assertIn("900", found[0].summary)
            ws.close()


class TestBrief(unittest.TestCase):
    def test_an_empty_record_says_so_plainly(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            text = brief(ws, now=T0)
            self.assertIn("Nothing was recorded", text)
            ws.close()

    def test_the_same_record_and_clock_produce_the_same_paragraph(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            lot = ws.new_lot(kind="extract", cultivar="X", weight="500", room="inv1", at=T0)
            ws.adjust_stock(lot.id, remove="2", cause="spillage", reason="jar", at=T0)
            first = brief(ws, now=T0 + timedelta(days=1))
            second = brief(ws, now=T0 + timedelta(days=1))
            self.assertEqual(first, second)
            ws.close()

    def test_singular_and_plural_both_read_like_english(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            lot = ws.new_lot(kind="extract", cultivar="X", weight="500", room="inv1", at=T0)
            ws.adjust_stock(lot.id, remove="2", cause="spillage", reason="jar", at=T0)
            text = brief(ws, now=T0 + timedelta(days=1))
            self.assertIn("1 correction was made", text)
            self.assertIn("is still waiting to go", text)
            self.assertNotIn("1 correction were", text)
            self.assertNotIn("1 record were", text)
            ws.close()

    def test_counts_and_words_agree_on_a_plural_period(self):
        with tempfile.TemporaryDirectory() as d:
            ws = workspace(Path(d))
            for i in range(2):
                lot = ws.new_lot(kind="extract", cultivar="X", weight="500", room="inv1",
                                 at=T0 + timedelta(hours=i))
                ws.adjust_stock(lot.id, remove="2", cause="spillage", reason="jar",
                                at=T0 + timedelta(hours=i))
            text = brief(ws, now=T0 + timedelta(days=1))
            self.assertIn("2 corrections were made", text)
            self.assertIn("are still waiting to go", text)
            ws.close()


if __name__ == "__main__":
    unittest.main()
