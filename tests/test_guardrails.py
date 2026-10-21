"""Guardrails fire on the conditions the research says get missed, and stay quiet otherwise."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from coontie import guardrails as g
from coontie import compliance as c
from coontie.model import Adjustment, Cultivar, FinalProduct, Lot, RoomId

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
CULT = Cultivar("Blue Dream")


def lot(lid="L1", hold=False):
    return Lot(
        id=lid,
        inventory_type="cured and dried flower",
        cultivar=CULT,
        quantity=Decimal("100"),
        unit="g",
        room_id=RoomId("R1"),
        on_hold=hold,
    )


def product(pid="P1", days=10, name="Blue Dream 3.5g"):
    return FinalProduct(
        id=pid,
        product_type="whole flower",
        approved_product_name=name,
        unique_product_id="BD-35-FL-INH",
        net_quantity=Decimal("3.5"),
        unit="g",
        expiration_date=T0 + timedelta(days=days),
        packaged_at=T0,
        room_id=RoomId("R2"),
        cultivar=CULT,
        unit_count=1,
    )


class TestHold(unittest.TestCase):
    def test_held_lot_alerts_and_blocks(self):
        a = g.lot_on_hold(lot(hold=True))
        self.assertIsNotNone(a)
        self.assertTrue(a.blocks)
        self.assertEqual(a.severity, c.Severity.VIOLATION)

    def test_clear_lot_is_silent(self):
        self.assertIsNone(g.lot_on_hold(lot()))


class TestExpiry(unittest.TestCase):
    def test_inside_window_warns(self):
        alerts = g.expiring_products([product(days=10)], T0, window_days=30)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, c.Severity.WARNING)

    def test_past_expiry_is_a_violation(self):
        alerts = g.expiring_products([product(days=-1)], T0)
        self.assertEqual(alerts[0].severity, c.Severity.VIOLATION)
        self.assertIn("EXPIRED", alerts[0].message)

    def test_outside_window_is_silent(self):
        self.assertEqual(g.expiring_products([product(days=90)], T0, window_days=30), [])


class TestAdjustments(unittest.TestCase):
    def test_exempt_cause_is_silent(self):
        a = Adjustment("L1", "recount", "processed", Decimal("1"), "g", "F1", T0, cause="processing")
        self.assertEqual(g.unjustified_adjustments([a]), [])

    def test_missing_justification_fires(self):
        a = Adjustment("L1", "recount", "shrinkage", Decimal("1"), "g", "F1", T0, cause="shrinkage")
        alerts = g.unjustified_adjustments([a])
        self.assertEqual(len(alerts), 1)
        self.assertIn("64-4.222(12)", alerts[0].citation)

    def test_timely_justification_is_silent(self):
        a = Adjustment(
            "L1", "recount", "shrinkage", Decimal("1"), "g", "F1", T0,
            cause="shrinkage", justification_sent_at=T0 + timedelta(hours=5),
        )
        self.assertEqual(g.unjustified_adjustments([a]), [])

    def test_late_justification_fires(self):
        a = Adjustment(
            "L1", "recount", "shrinkage", Decimal("1"), "g", "F1", T0,
            cause="shrinkage", justification_sent_at=T0 + timedelta(hours=13),
        )
        self.assertEqual(len(g.unjustified_adjustments([a])), 1)


class TestDisconnectClock(unittest.TestCase):
    def test_under_two_hours_warns_only(self):
        a = g.disconnect_clock(T0, T0 + timedelta(minutes=45))
        self.assertIsNotNone(a)
        self.assertEqual(a.severity, c.Severity.WARNING)

    def test_over_three_hours_unreported_blocks(self):
        a = g.disconnect_clock(T0, T0 + timedelta(hours=4))
        self.assertEqual(a.severity, c.Severity.VIOLATION)
        self.assertTrue(a.blocks)

    def test_reported_in_time_clears(self):
        a = g.disconnect_clock(
            T0, T0 + timedelta(hours=5),
            restored_at=T0 + timedelta(hours=5),
            notified_at=T0 + timedelta(hours=2, minutes=30),
        )
        self.assertIsNone(a)


class TestStaleLocation(unittest.TestCase):
    def test_unknown_room_fires(self):
        alerts = g.stale_locations([lot()], known_rooms={"R9"})
        self.assertEqual(len(alerts), 1)
        self.assertIn("64-4.222(11)", alerts[0].citation)

    def test_known_room_is_silent(self):
        self.assertEqual(g.stale_locations([lot()], known_rooms={"R1"}), [])


class TestCollect(unittest.TestCase):
    def test_blocking_items_come_first(self):
        a = Adjustment("L1", "recount", "shrinkage", Decimal("1"), "g", "F1", T0, cause="shrinkage")
        alerts = g.collect(
            lots=[lot("L1", hold=True)],
            products=[product(days=10)],
            adjustments=[a],
            now=T0,
        )
        self.assertGreaterEqual(len(alerts), 3)
        self.assertTrue(alerts[0].blocks)
        self.assertFalse(alerts[-1].blocks)

    def test_counts_by_guard(self):
        alerts = g.collect(lots=[lot("L1", hold=True), lot("L2", hold=True)], products=[], adjustments=[], now=T0)
        self.assertEqual(g.counts(alerts), {"lot_on_hold": 2})


if __name__ == "__main__":
    unittest.main()
