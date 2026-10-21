"""The DH5059 catalog must stay faithful to the form. These tests are the guard."""

import unittest

from mmtc_record.events import BY_KEY, EVENTS, Stage, Timing, events_for_stage, realtime_events


class TestCatalogShape(unittest.TestCase):
    def test_event_count_matches_the_form(self):
        # 5 cultivation + 9 processing + 3 dispensing + 4 location + 5 waste
        # + 3 transfer + 2 transport + 2 admin = 33
        self.assertEqual(len(EVENTS), 33)

    def test_keys_are_unique(self):
        keys = [e.key for e in EVENTS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_event_has_fields(self):
        for e in EVENTS:
            self.assertGreaterEqual(len(e.fields), 1, e.key)

    def test_every_event_cites_something(self):
        for e in EVENTS:
            self.assertTrue(e.citation, e.key)

    def test_stage_counts(self):
        self.assertEqual(len(events_for_stage(Stage.CULTIVATION)), 5)
        self.assertEqual(len(events_for_stage(Stage.PROCESSING)), 9)
        self.assertEqual(len(events_for_stage(Stage.DISPENSING)), 3)
        self.assertEqual(len(events_for_stage(Stage.LOCATION)), 4)
        self.assertEqual(len(events_for_stage(Stage.WASTE)), 5)
        self.assertEqual(len(events_for_stage(Stage.TRANSFER)), 3)
        self.assertEqual(len(events_for_stage(Stage.TRANSPORT)), 2)
        self.assertEqual(len(events_for_stage(Stage.ADMIN)), 2)

    def test_realtime_set(self):
        # Only dispensing-side and transfer-side records are real time in DH5059.
        self.assertEqual(
            {e.key for e in realtime_events()},
            {"dispensation", "refund", "void_sale", "transfer_out", "transfer_in"},
        )

    def test_disposal_scheduling_carries_the_72_hour_wait(self):
        waits = {e.key: e.wait_hours_before_next for e in EVENTS if e.wait_hours_before_next}
        self.assertEqual(waits, {"disposal_schedule_inventory": 72, "disposal_schedule_plants": 72})


class TestTranscription(unittest.TestCase):
    """Spot checks against specific lines of DH5059-OMMU-05/2026."""

    def test_seed_clone_batch(self):
        e = BY_KEY["seed_clone_batch"]
        for name in ("facility_location", "room", "cultivar", "count"):
            self.assertIn(name, e.required_names)
        self.assertNotIn("mother_plant_id", e.required_names)  # "if applicable"

    def test_immature_plant_records_mother_status_and_origin(self):
        e = BY_KEY["immature_plant"]
        self.assertIn("is_mother_plant", e.required_names)
        self.assertIn("origin_batch_id", e.required_names)

    def test_harvest_records_three_material_streams(self):
        e = BY_KEY["harvest"]
        for name in (
            "wet_flower_weight",
            "waste_weight",
            "other_material_weight",
            "post_harvest_room",
        ):
            self.assertIn(name, e.required_names)

    def test_final_product_field_set(self):
        e = BY_KEY["final_product"]
        for name in (
            "product_type",
            "expiration_date",
            "approved_product_name",
            "packaged_at",
            "unique_product_id",
            "weight_per_unit",
        ):
            self.assertIn(name, e.required_names)
        self.assertIn("cultivar", [f.name for f in e.fields if not f.required])

    def test_dispensation_field_set(self):
        e = BY_KEY["dispensation"]
        self.assertEqual(
            set(e.required_names),
            {
                "item_id",
                "sale_id",
                "product_class",
                "unique_product_id",
                "route_of_administration",
                "unit_count",
                "dispensing_facility_location",
                "patient_mmurnumber",
                "patient_dob",
                "price",
            },
        )
        self.assertEqual(e.timing, Timing.REALTIME)

    def test_manifest_has_route_and_stop_timing(self):
        e = BY_KEY["manifest"]
        for name in ("stops", "arrival_times", "departure_times", "route_directions", "vehicle_id"):
            self.assertIn(name, e.required_names)

    def test_api_user_carries_credentials_and_permissions(self):
        self.assertEqual(
            set(BY_KEY["api_user"].required_names), {"email", "password", "permissions"}
        )


if __name__ == "__main__":
    unittest.main()
