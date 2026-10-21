"""Drift classification: every difference gets a name, and a tolerance beats a guess."""

import unittest
from decimal import Decimal

from coontie.drift import Drift, compare


BASE = {"L1": {"quantity": 100, "status": "active"}}


class TestClasses(unittest.TestCase):
    def test_identical_snapshots_are_clean(self):
        r = compare(BASE, BASE)
        self.assertTrue(r.clean)
        self.assertEqual(r.ours_count, 1)
        self.assertEqual(r.theirs_count, 1)

    def test_missing_at_state(self):
        r = compare(BASE, {})
        self.assertEqual(r.items[0].kind, Drift.MISSING_AT_STATE)
        self.assertIn("we hold a record", r.items[0].note)

    def test_missing_locally(self):
        r = compare({}, BASE)
        self.assertEqual(r.items[0].kind, Drift.MISSING_LOCALLY)
        self.assertIn("state holds", r.items[0].note)

    def test_quantity_mismatch(self):
        r = compare(BASE, {"L1": {"quantity": 95, "status": "active"}})
        self.assertEqual(r.items[0].kind, Drift.QUANTITY_MISMATCH)
        self.assertIn("100 vs 95", r.items[0].note)

    def test_status_mismatch(self):
        r = compare(BASE, {"L1": {"quantity": 100, "status": "on_hold"}})
        self.assertEqual(r.items[0].kind, Drift.STATUS_MISMATCH)

    def test_quantity_wins_over_status_when_both_differ(self):
        r = compare(BASE, {"L1": {"quantity": 90, "status": "on_hold"}})
        self.assertEqual([i.kind for i in r.items], [Drift.QUANTITY_MISMATCH])


class TestTolerance(unittest.TestCase):
    def test_unit_conversion_noise_is_not_drift(self):
        ours = {"L1": {"quantity": "28.3495"}}
        theirs = {"L1": {"quantity": "28.33"}}
        self.assertTrue(compare(ours, theirs, quantity_tolerance="0.05").clean)

    def test_a_real_gap_still_fires(self):
        ours = {"L1": {"quantity": "28.3495"}}
        theirs = {"L1": {"quantity": "27.00"}}
        self.assertFalse(compare(ours, theirs, quantity_tolerance="0.05").clean)

    def test_zero_tolerance_is_the_default(self):
        r = compare({"L1": {"quantity": "1.00"}}, {"L1": {"quantity": "1.01"}})
        self.assertFalse(r.clean)


class TestReport(unittest.TestCase):
    def test_summary_names_the_kinds(self):
        r = compare(
            {"L1": {"quantity": 100}, "L2": {"quantity": 5}},
            {"L1": {"quantity": 90}, "L3": {"quantity": 7}},
        )
        self.assertIn("quantity mismatch", r.summary())
        self.assertIn("missing", r.summary())
        self.assertEqual(r.by_kind()["quantity_mismatch"], 1)

    def test_clean_summary(self):
        self.assertIn("no drift", compare(BASE, BASE).summary())

    def test_ordering_is_deterministic(self):
        a = compare({"B": {"quantity": 1}, "A": {"quantity": 1}}, {})
        b = compare({"A": {"quantity": 1}, "B": {"quantity": 1}}, {})
        self.assertEqual([i.key for i in a.items], [i.key for i in b.items])


class TestScalars(unittest.TestCase):
    def test_scalar_snapshots_are_accepted(self):
        r = compare({"L1": 100}, {"L1": 100})
        self.assertTrue(r.clean)

    def test_scalar_gap_fires(self):
        r = compare({"L1": Decimal("100")}, {"L1": Decimal("99")})
        self.assertEqual(r.items[0].kind, Drift.QUANTITY_MISMATCH)


if __name__ == "__main__":
    unittest.main()
