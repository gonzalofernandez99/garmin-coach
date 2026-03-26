"""Tests for activity helper functions."""

from __future__ import annotations

import unittest

from garmin_coach.utils.activities import (
    activity_list_from_payload,
    dedupe_activities,
    extract_activity_id,
    extract_activity_start,
)


class ActivityUtilsTest(unittest.TestCase):
    def test_extract_activity_id_from_summary(self) -> None:
        activity = {"activityId": 123456}
        self.assertEqual(extract_activity_id(activity), "123456")

    def test_extract_activity_start_from_nested_summary(self) -> None:
        activity = {
            "summaryDTO": {
                "startTimeLocal": "2026-03-24 07:15:00",
            }
        }
        parsed = extract_activity_start(activity)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.isoformat(), "2026-03-24T07:15:00")

    def test_dedupe_activities(self) -> None:
        activities = [
            {"activityId": 1, "name": "A"},
            {"activityId": 1, "name": "B"},
            {"activityId": 2, "name": "C"},
        ]
        deduped = dedupe_activities(activities)
        self.assertEqual([item["activityId"] for item in deduped], [1, 2])

    def test_activity_list_from_payload(self) -> None:
        payload = {"activities": [{"activityId": 1}, {"activityId": 2}]}
        activities = activity_list_from_payload(payload)
        self.assertEqual(len(activities), 2)


if __name__ == "__main__":
    unittest.main()
