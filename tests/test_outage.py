"""The disconnection clock: thresholds, statuses, drafts, and the outage CSV."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from coontie import compliance as c
from coontie.outage import (
    REPORT_COLUMNS,
    Outage,
    notice_draft,
    render_dispensations_csv,
    restoration_draft,
)

T0 = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)


def outage(restored=None) -> Outage:
    return Outage(id="out-1", facility_id="fac-1", started_at=T0, restored_at=restored)


class TestThresholds(unittest.TestCase):
    def test_constants_match_the_rule(self):
        self.assertEqual(c.DISCONNECT_THRESHOLD, timedelta(hours=2))
        self.assertEqual(c.DISCONNECT_NOTICE_DEADLINE, timedelta(hours=3))
        self.assertEqual(c.OUTAGE_CSV_DEADLINE, timedelta(hours=24))

    def test_exactly_two_hours_is_not_yet_due(self):
        o = outage()
        self.assertEqual(o.notice_status(T0 + timedelta(hours=2)), "not_due")
        self.assertFalse(o.notice_is_due(T0 + timedelta(hours=2)))

    def test_one_minute_past_two_hours_is_due(self):
        o = outage()
        self.assertEqual(o.notice_status(T0 + timedelta(hours=2, minutes=1)), "due")
        self.assertTrue(o.notice_is_due(T0 + timedelta(hours=2, minutes=1)))

    def test_after_three_hours_unsent_is_late(self):
        self.assertEqual(outage().notice_status(T0 + timedelta(hours=3, minutes=1)), "late")

    def test_sent_within_three_hours_is_on_time(self):
        o = Outage(id="out-1", facility_id="fac-1", started_at=T0, notice_sent_at=T0 + timedelta(hours=2, minutes=30))
        self.assertEqual(o.notice_status(T0 + timedelta(hours=5)), "sent_on_time")

    def test_sent_after_three_hours_is_late(self):
        o = Outage(id="out-1", facility_id="fac-1", started_at=T0, notice_sent_at=T0 + timedelta(hours=4))
        self.assertEqual(o.notice_status(T0 + timedelta(hours=5)), "sent_late")


class TestReportClock(unittest.TestCase):
    def test_open_outage_has_no_report(self):
        self.assertEqual(outage().report_status(), "not_restored")
        self.assertIsNone(outage().report_deadline)

    def test_deadline_is_24_hours_after_restoration(self):
        O = outage(restored=T0 + timedelta(hours=5))
        self.assertEqual(O.report_deadline, T0 + timedelta(hours=29))

    def test_due_then_ready_then_late(self):
        restored = T0 + timedelta(hours=5)
        o = outage(restored=restored)
        self.assertEqual(o.report_status(restored), "due")
        ready = Outage(
            id="out-1", facility_id="fac-1", started_at=T0, restored_at=restored,
            report_created_at=restored, report_rows=2,
        )
        self.assertEqual(ready.report_status(restored + timedelta(hours=1)), "ready")
        self.assertEqual(o.report_status(restored + timedelta(hours=25)), "late")

    def test_sent_late_is_flagged(self):
        restored = T0 + timedelta(hours=5)
        o = Outage(
            id="out-1", facility_id="fac-1", started_at=T0, restored_at=restored,
            report_sent_at=restored + timedelta(hours=25),
        )
        self.assertEqual(o.report_status(restored + timedelta(hours=30)), "sent_late")


class TestDrafts(unittest.TestCase):
    def test_notice_cites_the_rule_and_the_deadline(self):
        subject, body = notice_draft(
            outage(), mmtc_name="Nature's Grace", license_number="MMTC-2026-0030",
            dispensations=2, now=T0 + timedelta(hours=2, minutes=1),
        )
        for needle in (
            "64-4.222(2)", "ommu_seedtosale@flhealth.gov", "MMTC-2026-0030",
            "2h01m", "3 hours after the disconnection began", "Dispensations recorded during the disconnection so far: 2",
            "64-4.222(2)(a)", "64-4.222(2)(b)",
        ):
            self.assertIn(needle, body, needle)
        self.assertIn("Nature's Grace", subject)

    def test_notice_claims_nothing_about_restoration(self):
        _, body = notice_draft(outage(), mmtc_name="X", license_number="L", dispensations=0, now=T0 + timedelta(hours=3))
        self.assertIn("has not been restored as of this notice", body)
        self.assertIn("No dispensing has occurred", body)

    def test_restoration_draft_reports_duration(self):
        restored = T0 + timedelta(hours=5)
        subject, body = restoration_draft(
            outage(restored=restored), mmtc_name="X", license_number="L", dispensations=3
        )
        self.assertIn("Restoration of connection", subject)
        self.assertIn("5h00m", body)
        self.assertIn("Dispensations during the outage: 3", body)
        self.assertIn("64-4.222(2)(b)", body)


class TestOutageCsv(unittest.TestCase):
    def test_columns_are_the_rules_minimum(self):
        self.assertEqual(REPORT_COLUMNS[0], "Date and Time of Dispensation")
        self.assertEqual(REPORT_COLUMNS[1], "Patient ID Number")
        self.assertEqual(REPORT_COLUMNS[2], "Department Seed-to-Sale Inventory Identification Number")
        self.assertEqual(REPORT_COLUMNS[3], "Weight Dispensed")
        self.assertEqual(REPORT_COLUMNS[5], "Dispensing Facility Location")

    def test_rows_render_with_iso_timestamps_and_quoted_text(self):
        text = render_dispensations_csv(
            [
                {
                    "dispensed_at": T0, "patient_id": "MMUR1", "inventory_id": "FL-1",
                    "weight": Decimal("3.5"), "unit": "g", "location": "Store, Tampa",
                }
            ]
        )
        lines = text.splitlines()
        self.assertEqual(lines[0], ",".join(REPORT_COLUMNS))
        self.assertIn("2026-10-21T08:00:00Z", lines[1])
        self.assertIn('"Store, Tampa"', lines[1])

    def test_empty_outage_still_produces_a_header(self):
        self.assertEqual(render_dispensations_csv([]).count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
