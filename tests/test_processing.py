"""Processing arithmetic: conservation, conversion limits, the immutable expiration."""

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from coontie.processing import (
    FinalProduct,
    StockLot,
    amount,
    check_conversion,
    check_expiration,
    check_removal,
    cmtl_note,
    expiration_conflict,
    parse_csv_list,
    remaining,
)

T0 = datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc)


def lot(original="600") -> StockLot:
    return StockLot(id="stk-1", kind="cured and dried flower", cultivar="Blue Dream", room_id="inv1",
                    original=Decimal(original), unit="g")


class TestRemaining(unittest.TestCase):
    def test_no_moves_means_all_of_it(self):
        self.assertEqual(remaining(Decimal("600"), []), Decimal("600"))

    def test_moves_subtract(self):
        self.assertEqual(remaining(Decimal("600"), [Decimal("200"), Decimal("300"), Decimal("5")]), Decimal("95"))


class TestRemoval(unittest.TestCase):
    def test_fine(self):
        check_removal(lot(), Decimal("600"), Decimal("200"))

    def test_exactly_all_of_it_is_allowed(self):
        check_removal(lot(), Decimal("600"), Decimal("600"))

    def test_more_than_held_is_refused_with_both_numbers(self):
        with self.assertRaises(ValueError) as ctx:
            check_removal(lot(), Decimal("100"), Decimal("500"))
        message = str(ctx.exception)
        self.assertIn("100", message)
        self.assertIn("500", message)

    def test_zero_is_refused(self):
        with self.assertRaises(ValueError):
            check_removal(lot(), Decimal("100"), Decimal("0"))


class TestConversion(unittest.TestCase):
    def test_result_plus_waste_within_removed(self):
        check_conversion(Decimal("300"), Decimal("90"), Decimal("15"))

    def test_exactly_all_of_it_is_allowed(self):
        check_conversion(Decimal("300"), Decimal("285"), Decimal("15"))

    def test_more_out_than_in_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            check_conversion(Decimal("300"), Decimal("290"), Decimal("20"))
        self.assertIn("exceeds", str(ctx.exception))

    def test_negative_is_refused(self):
        with self.assertRaises(ValueError):
            check_conversion(Decimal("300"), Decimal("-1"), Decimal("0"))


class TestExpiration(unittest.TestCase):
    def test_must_be_after_packaging(self):
        check_expiration(T0, date(2027, 6, 10))

    def test_same_day_is_refused(self):
        with self.assertRaises(ValueError):
            check_expiration(T0, date(2026, 12, 10))

    def test_no_conflict_when_nothing_recorded(self):
        self.assertIsNone(expiration_conflict(None, date(2027, 6, 10)))

    def test_same_date_is_not_a_conflict(self):
        existing = FinalProduct(
            id="fin-1", lot_id="stk-1", upid="U", product_type="Whole Flower", cultivar="X",
            unit_count=1, net_weight=Decimal("3.5"), unit="g", weight_per_unit=None,
            approved_name="X", packaged_at=T0, expiration_date=date(2027, 6, 10), room_id="inv1",
        )
        self.assertIsNone(expiration_conflict(existing, date(2027, 6, 10)))

    def test_a_different_date_is_refused_and_quotes_immutable(self):
        existing = FinalProduct(
            id="fin-1", lot_id="stk-1", upid="U", product_type="Whole Flower", cultivar="X",
            unit_count=1, net_weight=Decimal("3.5"), unit="g", weight_per_unit=None,
            approved_name="X", packaged_at=T0, expiration_date=date(2027, 6, 10), room_id="inv1",
        )
        message = expiration_conflict(existing, date(2027, 9, 10))
        self.assertIn("2027-06-10", message)
        self.assertIn("immutable", message)
        self.assertIn("2027-09-10", message)


class TestHelpers(unittest.TestCase):
    def test_amounts(self):
        self.assertEqual(amount("1,800 g"), Decimal("1800"))

    def test_csv_lists(self):
        self.assertEqual(parse_csv_list("MCT oil, Natural flavor"), ["MCT oil", "Natural flavor"])

    def test_known_lab_gets_no_note(self):
        self.assertEqual(cmtl_note("ACS Laboratory"), "")

    def test_unknown_lab_gets_a_note_not_a_refusal(self):
        self.assertIn("approved list", cmtl_note("Some Lab LLC"))


if __name__ == "__main__":
    unittest.main()
