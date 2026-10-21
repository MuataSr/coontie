"""Cultivation logic: plant ids, the schedule rule, the 72-hour wait, harvest arithmetic."""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from coontie import compliance as c
from coontie.cultivation import (
    Harvest,
    Plant,
    amount,
    check_harvest_weights,
    describe_open_schedules,
    matching_schedule,
    parse_plants,
    plant_id,
    require_disposal_wait,
    require_growing,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


class TestPlantIds(unittest.TestCase):
    def test_ranges_and_lists(self):
        self.assertEqual(parse_plants("PL-0001..PL-0003"), ("PL-0001", "PL-0002", "PL-0003"))
        self.assertEqual(parse_plants("PL-0001,PL-0002"), ("PL-0001", "PL-0002"))
        self.assertEqual(parse_plants("1..2"), ("PL-0001", "PL-0002"))
        self.assertEqual(parse_plants("pl-7"), ("PL-0007",))

    def test_duplicates_are_refused(self):
        with self.assertRaises(ValueError):
            parse_plants("PL-0001,PL-0001")

    def test_nonsense_is_refused_with_the_expected_shape(self):
        with self.assertRaises(ValueError) as ctx:
            parse_plants("the big one")
        self.assertIn("PL-0001", str(ctx.exception))

    def test_backwards_range_is_refused(self):
        with self.assertRaises(ValueError):
            parse_plants("PL-0005..PL-0002")

    def test_empty_is_refused(self):
        with self.assertRaises(ValueError):
            parse_plants("   ")

    def test_ids_are_padded(self):
        self.assertEqual(plant_id(7), "PL-0007")
        self.assertEqual(plant_id(1234), "PL-1234")


class TestAmounts(unittest.TestCase):
    def test_units_and_commas_are_stripped(self):
        self.assertEqual(amount("1,800 g"), Decimal("1800"))
        self.assertEqual(amount("40"), Decimal("40"))

    def test_words_are_refused(self):
        with self.assertRaises(ValueError):
            amount("a lot")


class TestGrowing(unittest.TestCase):
    def plants(self):
        return {
            "PL-0001": Plant(id="PL-0001", batch_id="b", cultivar="X", room_id="r", state="immature"),
            "PL-0002": Plant(id="PL-0002", batch_id="b", cultivar="X", room_id="r", state="harvested"),
        }

    def test_growing_passes(self):
        require_growing(self.plants(), ("PL-0001",))

    def test_unknown_plant_is_named(self):
        with self.assertRaises(ValueError) as ctx:
            require_growing(self.plants(), ("PL-9999",))
        self.assertIn("PL-9999", str(ctx.exception))

    def test_harvested_plant_is_refused_with_its_state(self):
        with self.assertRaises(ValueError) as ctx:
            require_growing(self.plants(), ("PL-0002",))
        self.assertIn("harvested", str(ctx.exception))


def harvest(ids, scheduled=True, completed=False) -> Harvest:
    return Harvest(
        id="hrv-1", room_id="r", post_harvest_room_id="d", plant_ids=tuple(ids),
        wet_weight=Decimal("0"), wet_unit="g", waste_weight=Decimal("0"), waste_unit="g",
        other_weight=Decimal("0"), other_unit="g",
        scheduled_at=T0 if scheduled else None, harvested_at=T0 if completed else None,
    )


class TestSchedule(unittest.TestCase):
    def test_exact_set_matches(self):
        h = harvest(["PL-0001", "PL-0002"])
        self.assertIs(matching_schedule([h], ("PL-0002", "PL-0001")), h)

    def test_a_subset_does_not_match(self):
        h = harvest(["PL-0001", "PL-0002"])
        self.assertIsNone(matching_schedule([h], ("PL-0001",)))

    def test_a_completed_schedule_does_not_match(self):
        h = harvest(["PL-0001"], completed=True)
        self.assertIsNone(matching_schedule([h], ("PL-0001",)))

    def test_open_schedules_are_described(self):
        self.assertEqual(describe_open_schedules([]), "none")
        self.assertIn("2 plants", describe_open_schedules([harvest(["PL-0001", "PL-0002"])]))


class TestDisposalWait(unittest.TestCase):
    def test_the_wait_is_72_hours(self):
        self.assertEqual(c.DISPOSAL_WAIT, timedelta(hours=72))

    def test_too_early_is_refused_and_says_how_long(self):
        with self.assertRaises(ValueError) as ctx:
            require_disposal_wait(T0, T0 + timedelta(hours=48))
        self.assertIn("24h remain", str(ctx.exception))

    def test_exactly_72_hours_passes(self):
        require_disposal_wait(T0, T0 + timedelta(hours=72))

    def test_later_passes(self):
        require_disposal_wait(T0, T0 + timedelta(days=4))


class TestHarvestWeights(unittest.TestCase):
    def test_sane_weights_pass(self):
        check_harvest_weights(Decimal("1800"), Decimal("240"), Decimal("60"))

    def test_zero_wet_is_refused(self):
        with self.assertRaises(ValueError):
            check_harvest_weights(Decimal("0"), Decimal("0"), Decimal("0"))

    def test_waste_plus_other_over_wet_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            check_harvest_weights(Decimal("100"), Decimal("80"), Decimal("40"))
        self.assertIn("exceeds", str(ctx.exception))

    def test_negative_is_refused(self):
        with self.assertRaises(ValueError):
            check_harvest_weights(Decimal("100"), Decimal("-1"), Decimal("0"))


if __name__ == "__main__":
    unittest.main()
