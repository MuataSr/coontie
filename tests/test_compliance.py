"""Each rule check returns the right verdict at the boundary stated in the rule."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from mmtc_record import compliance as c

T0 = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class TestEventTiming(unittest.TestCase):
    def test_twelve_hour_window_passes_inside(self):
        self.assertIsNone(c.check_event_timing("12h", T0, T0 + timedelta(hours=11, minutes=59)))

    def test_twelve_hour_window_fails_outside(self):
        f = c.check_event_timing("12h", T0, T0 + timedelta(hours=12, minutes=1))
        self.assertIsNotNone(f)
        self.assertEqual(f.rule_id, "PROC-4")
        self.assertEqual(f.severity, c.Severity.VIOLATION)

    def test_realtime_allows_only_a_minute(self):
        self.assertIsNone(c.check_event_timing("realtime", T0, T0 + timedelta(seconds=59)))
        self.assertIsNotNone(c.check_event_timing("realtime", T0, T0 + timedelta(minutes=5)))


class TestHarvestAndDisposal(unittest.TestCase):
    def test_harvest_needs_a_prior_schedule(self):
        self.assertIsNone(c.check_harvest_scheduled(T0, T0 - timedelta(hours=1)))
        self.assertIsNotNone(c.check_harvest_scheduled(T0, None))
        self.assertIsNotNone(c.check_harvest_scheduled(T0, T0 + timedelta(minutes=1)))

    def test_disposal_waits_72_hours(self):
        self.assertIsNone(c.check_disposal_wait(T0, T0 + timedelta(hours=72)))
        self.assertIsNotNone(c.check_disposal_wait(T0, T0 + timedelta(hours=71, minutes=59)))


class TestFinalProduct(unittest.TestCase):
    def test_expiration_is_immutable(self):
        self.assertIsNone(c.check_expiration_immutable(T0, T0))
        self.assertIsNotNone(c.check_expiration_immutable(T0, T0 + timedelta(days=1)))


class TestAdjustments(unittest.TestCase):
    def test_exempt_causes_need_nothing(self):
        for cause in ("processing", "dispensation", "wholesale_purchase", "wholesale_distribution", "waste_disposal"):
            self.assertIsNone(c.check_adjustment_justification(T0, cause, None))

    def test_unexplained_adjustment_without_justification_is_a_violation(self):
        f = c.check_adjustment_justification(T0, "shrinkage", None)
        self.assertIsNotNone(f)
        self.assertEqual(f.rule_id, "PROC-13")

    def test_justification_inside_twelve_hours_passes(self):
        self.assertIsNone(
            c.check_adjustment_justification(T0, "shrinkage", T0 + timedelta(hours=11, minutes=59))
        )

    def test_late_justification_fails(self):
        self.assertIsNotNone(
            c.check_adjustment_justification(T0, "shrinkage", T0 + timedelta(hours=12, minutes=1))
        )


class TestRoutes(unittest.TestCase):
    def test_single_approved_route_is_clean(self):
        self.assertEqual(c.check_dispensation_routes(["inhalation"], {"inhalation"}), [])

    def test_two_routes_is_a_violation(self):
        findings = c.check_dispensation_routes(["inhalation", "oral"], {"inhalation", "oral"})
        self.assertTrue(any(f.rule_id == "PROC-8" for f in findings))

    def test_unapproved_route_is_a_violation(self):
        findings = c.check_dispensation_routes(["oral"], {"inhalation"})
        self.assertEqual(len(findings), 1)
        self.assertIn("oral", findings[0].message)


class TestDisconnection(unittest.TestCase):
    def test_short_outage_needs_nothing(self):
        self.assertEqual(c.check_disconnect(T0, T0 + timedelta(hours=2), None), [])

    def test_long_outage_reported_in_time_passes(self):
        restored = T0 + timedelta(hours=5)
        self.assertEqual(c.check_disconnect(T0, restored, T0 + timedelta(hours=2, minutes=59)), [])

    def test_long_outage_reported_late_fails(self):
        restored = T0 + timedelta(hours=5)
        findings = c.check_disconnect(T0, restored, T0 + timedelta(hours=3, minutes=1))
        self.assertTrue(findings)
        self.assertEqual(findings[0].rule_id, "PROC-1")

    def test_unreported_long_outage_fails(self):
        restored = T0 + timedelta(hours=5)
        self.assertTrue(c.check_disconnect(T0, restored, None))

    def test_outage_csv_within_24_hours(self):
        self.assertIsNone(c.check_outage_report(T0, T0 + timedelta(hours=24)))
        self.assertIsNotNone(c.check_outage_report(T0, T0 + timedelta(hours=25)))
        self.assertIsNotNone(c.check_outage_report(T0, None))


class TestDepartmentRequests(unittest.TestCase):
    def test_native_csv_within_48_hours(self):
        self.assertIsNone(c.check_department_csv(T0, T0 + timedelta(hours=48)))
        self.assertIsNotNone(c.check_department_csv(T0, T0 + timedelta(hours=49)))

    def test_retention_floor_is_three_years(self):
        self.assertEqual(c.retention_floor(datetime(2029, 10, 21, tzinfo=timezone.utc)).year, 2026)


class TestAccess(unittest.TestCase):
    def test_authorized_roles(self):
        for role in ("mmtc_owner", "mmtc_employee", "internal_sts_vendor", "department_sts_vendor"):
            self.assertIsNone(c.check_access(role))

    def test_third_party_is_refused(self):
        f = c.check_access("third_party_auditor")
        self.assertIsNotNone(f)
        self.assertEqual(f.rule_id, "PROC-6")


class TestConversion(unittest.TestCase):
    def test_one_ounce_is_about_28_grams(self):
        self.assertEqual(c.ounces_to_grams(1).quantize(Decimal("0.01")), Decimal("28.33"))

    def test_round_trip(self):
        self.assertAlmostEqual(float(c.grams_to_ounces(c.ounces_to_grams(10))), 10.0, places=6)


class TestIntegrationPlan(unittest.TestCase):
    def test_missing_items_are_named(self):
        missing = c.missing_integration_plan_items({"contact_name_phone_email": "x", "internal_sts_system_name": "y"})
        self.assertIn("contingency_plan_while_disconnected", missing)
        self.assertIn("unique_product_id_inventory_form", missing)
        self.assertNotIn("contact_name_phone_email", missing)

    def test_complete_plan_is_empty(self):
        self.assertEqual(c.missing_integration_plan_items({k: "x" for k in c.INTEGRATION_PLAN_REQUIRED}), [])


if __name__ == "__main__":
    unittest.main()
