"""Correction logic: causes, deadlines, status, and the draft notice's content."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from coontie import compliance as c
from coontie.amendments import (
    ALL_CAUSES,
    NON_EXEMPT_CAUSES,
    Amendment,
    draft_text,
    is_exempt,
    validate_cause,
)

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def amendment(cause="miscount", when=T0) -> Amendment:
    return Amendment(
        id="amd-1", target_kind="lot", target_id="lot-1", field="quantity",
        before="120", after="118", cause=cause, reason="physical recount",
        actor="C.Hurley", occurred_at=when, facility_id="fac-1", unit="g",
    )


class TestCauses(unittest.TestCase):
    def test_exempt_set_is_the_rules_own_list(self):
        for cause in c.EXEMPT_ADJUSTMENT_CAUSES:
            self.assertTrue(is_exempt(cause))
            self.assertIn(cause, ALL_CAUSES)

    def test_non_exempt_causes_are_not_exempt(self):
        for cause in NON_EXEMPT_CAUSES:
            self.assertFalse(is_exempt(cause))

    def test_unknown_cause_is_refused(self):
        with self.assertRaises(ValueError):
            validate_cause("wishful")

    def test_every_cause_is_validatable(self):
        for cause in ALL_CAUSES:
            self.assertEqual(validate_cause(cause), cause)


class TestDeadline(unittest.TestCase):
    def test_deadline_is_twelve_hours(self):
        self.assertEqual(amendment().deadline, T0 + timedelta(hours=12))

    def test_exempt_needs_no_justification(self):
        a = amendment(cause="processing")
        self.assertTrue(a.exempt)
        self.assertFalse(a.requires_justification)
        self.assertEqual(a.status(), "exempt")

    def test_pending_then_overdue(self):
        a = amendment()
        self.assertEqual(a.status(T0 + timedelta(hours=1)), "pending")
        self.assertEqual(a.status(T0 + timedelta(hours=13)), "overdue")


class TestDelta(unittest.TestCase):
    def test_negative_delta(self):
        self.assertEqual(amendment().delta, Decimal("-2"))

    def test_non_numeric_change_does_not_explode(self):
        a = Amendment(
            id="x", target_kind="lot", target_id="lot-1", field="on_hold",
            before="0", after="1", cause="contamination", reason="lab flag",
            actor="", occurred_at=T0, unit="",
        )
        self.assertEqual(a.delta, Decimal("0"))


class TestDraft(unittest.TestCase):
    def test_draft_carries_everything_the_department_needs(self):
        subject, body = draft_text(
            amendment(), mmtc_name="Nature's Grace FL, LLC", license_number="MMTC-2026-0030",
            product_name="Blue Dream 3.5g", upid="blue-dream-3.5-smoking-DE1114",
        )
        self.assertIn("Blue Dream 3.5g", subject)
        for needle in (
            "64-4.222(12)",
            "ommu_seedtosale@flhealth.gov",
            "MMTC-2026-0030",
            "blue-dream-3.5-smoking-DE1114",
            "120 g to 118 g",
            "-2 g",
            "miscount",
            "physical recount",
            "64-4.222(4)",
        ):
            self.assertIn(needle, body, needle)

    def test_draft_is_plain_and_does_not_overclaim(self):
        _, body = draft_text(amendment(), mmtc_name="X", license_number="L", product_name="P", upid="U")
        for word in ("apolog", "unfortunately", "guarantee"):
            self.assertNotIn(word, body.lower())

    def test_extra_context_is_appended_last(self):
        _, body = draft_text(
            amendment(), mmtc_name="X", license_number="L", product_name="P", upid="U",
            extra="Scale calibration certificate attached.",
        )
        self.assertTrue(body.rstrip().endswith("Scale calibration certificate attached."))


if __name__ == "__main__":
    unittest.main()
