"""Tests for date helpers."""

from __future__ import annotations

import unittest

from garmin_coach.utils.dates import inclusive_date_range, parse_iso_date


class DateUtilsTest(unittest.TestCase):
    def test_parse_iso_date(self) -> None:
        parsed = parse_iso_date("2026-03-24")
        self.assertEqual(parsed.isoformat(), "2026-03-24")

    def test_inclusive_date_range(self) -> None:
        dates = inclusive_date_range(
            parse_iso_date("2026-03-22"),
            parse_iso_date("2026-03-24"),
        )
        self.assertEqual(
            [item.isoformat() for item in dates],
            ["2026-03-22", "2026-03-23", "2026-03-24"],
        )

    def test_inclusive_date_range_rejects_invalid_order(self) -> None:
        with self.assertRaises(ValueError):
            inclusive_date_range(
                parse_iso_date("2026-03-24"),
                parse_iso_date("2026-03-22"),
            )


if __name__ == "__main__":
    unittest.main()
