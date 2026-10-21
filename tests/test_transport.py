"""Transport: what the statute requires on a manifest, and what it forbids outright."""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from coontie.transport import (
    MIN_CREW,
    REQUIRED_ITEMS,
    Manifest,
    ManifestItem,
    Vehicle,
    amount,
    parse_crew,
    render_manifest,
    validate_manifest,
)

T0 = datetime(2026, 12, 15, 8, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 12, 15, 11, 30, tzinfo=timezone.utc)

VAN = Vehicle(id="veh-1", name="White Transit", vin="1FTBW2CM5NKA00000", plate="FL-MMTC-12",
              make="Ford", model="Transit", year="2024", color="white")
MANIFEST = Manifest(
    id="man-1", facility_id="fac-1", recipient_name="Tampa Dispensary",
    recipient_address="900 N Tampa St, Tampa FL", vehicle_id="veh-1",
    employee_ids=("Maria Lopez", "Dev Patel"), departure_at=T0, arrival_at=T1,
    route="SR-50 west to I-75 south", stops=("Brooksville facility", "Tampa Dispensary"),
)
ITEMS = [ManifestItem(lot_id="stk-1", quantity=Decimal("200"), unit="g", form="cured and dried flower")]


def check(**overrides):
    kwargs = dict(
        recipient_name="Tampa Dispensary", recipient_address="900 N Tampa St, Tampa FL",
        vehicle=VAN, employee_ids=("Maria Lopez", "Dev Patel"), departure_at=T0, arrival_at=T1,
        items=ITEMS,
    )
    kwargs.update(overrides)
    return validate_manifest(**kwargs)


class TestStatutoryItems(unittest.TestCase):
    def test_the_statute_lists_seven_items(self):
        self.assertEqual(len(REQUIRED_ITEMS), 7)
        self.assertEqual([letter for letter, _ in REQUIRED_ITEMS], list("abcdefg"))

    def test_the_page_carries_every_one_of_them(self):
        page = render_manifest(
            MANIFEST, facility_name="Nature's Grace FL, LLC", facility_address="1200 Grove Rd, Brooksville FL",
            license_number="MMTC-2026-0030", vehicle=VAN,
            items=[(ITEMS[0], "cured and dried flower Blue Dream (lot stk-1)")],
            crew=MANIFEST.employee_ids,
        )
        for letter, text in REQUIRED_ITEMS:
            self.assertIn(f"({letter})", page)
        self.assertIn("2026-12-15 08:00 UTC", page)              # a
        self.assertIn("MMTC-2026-0030", page)                    # b
        self.assertIn("Tampa Dispensary", page)                  # c
        self.assertIn("200 g", page)                             # d
        self.assertIn("2026-12-15 11:30 UTC", page)              # e
        self.assertIn("FL-MMTC-12", page)                        # f
        self.assertIn("Maria Lopez", page)                       # g
        self.assertIn("signature", page)
        self.assertIn("three years", page)

    def test_the_page_names_the_rule_it_is_generated_under(self):
        page = render_manifest(
            MANIFEST, facility_name="X", facility_address="Y", license_number="L", vehicle=VAN,
            items=[(ITEMS[0], "flower (lot stk-1)")], crew=MANIFEST.employee_ids,
        )
        self.assertIn("64-4.222(10)", page)
        self.assertIn("381.986(8)(g)", page)


class TestRefusals(unittest.TestCase):
    def test_a_good_manifest_passes(self):
        check()

    def test_one_person_is_refused_with_the_statute(self):
        with self.assertRaises(ValueError) as ctx:
            check(employee_ids=("Maria Lopez",))
        message = str(ctx.exception)
        self.assertIn("at least two employees", message)
        self.assertIn("381.986(8)(g)5", message)

    def test_the_minimum_crew_is_two(self):
        self.assertEqual(MIN_CREW, 2)

    def test_an_unregistered_vehicle_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            check(vehicle=None)
        self.assertIn("381.986(8)(g)1.f", str(ctx.exception))

    def test_an_out_of_service_vehicle_is_refused(self):
        broken = Vehicle(**{**VAN.__dict__, "in_service": False})
        with self.assertRaises(ValueError) as ctx:
            check(vehicle=broken)
        self.assertIn("good working order", str(ctx.exception))

    def test_no_recipient_or_address(self):
        with self.assertRaises(ValueError):
            check(recipient_name="  ")
        with self.assertRaises(ValueError):
            check(recipient_address="")

    def test_no_departure_or_arrival(self):
        with self.assertRaises(ValueError):
            check(departure_at=None)
        with self.assertRaises(ValueError):
            check(arrival_at=None)

    def test_arrival_before_departure_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            check(arrival_at=datetime(2026, 12, 14, 8, 0, tzinfo=timezone.utc))
        self.assertIn("cannot precede", str(ctx.exception))

    def test_no_items_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            check(items=[])
        self.assertIn("at least one item", str(ctx.exception))

    def test_zero_quantity_is_refused(self):
        with self.assertRaises(ValueError):
            check(items=[ManifestItem(lot_id="stk-1", quantity=Decimal("0"), unit="g", form="flower")])

    def test_every_problem_is_reported_at_once(self):
        with self.assertRaises(ValueError) as ctx:
            check(employee_ids=(), items=[], recipient_name="")
        message = str(ctx.exception)
        self.assertIn("recipient", message)
        self.assertIn("two employees", message)
        self.assertIn("at least one item", message)


class TestHelpers(unittest.TestCase):
    def test_crew_parsing(self):
        self.assertEqual(parse_crew("Maria Lopez; Dev Patel"), ("Maria Lopez", "Dev Patel"))
        self.assertEqual(parse_crew("A, B , C"), ("A", "B", "C"))
        self.assertEqual(parse_crew(""), ())

    def test_amounts(self):
        self.assertEqual(amount("200"), Decimal("200"))
        self.assertEqual(amount("1,200 g"), Decimal("1200"))


if __name__ == "__main__":
    unittest.main()
