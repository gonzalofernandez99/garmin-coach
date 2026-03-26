"""Tests for CLI helper output sanitization."""

from __future__ import annotations

import unittest

from garmin_coach.cli import (
    _summarize_schedule_response,
    _summarize_workout_upload_response,
)


class CliHelperTest(unittest.TestCase):
    def test_workout_upload_summary_omits_author_metadata(self) -> None:
        payload = {
            "workoutId": 123,
            "workoutName": "Intervals",
            "sportType": {"sportTypeKey": "running"},
            "createdDate": "2026-03-25T22:03:23.0",
            "updatedDate": "2026-03-25T22:03:23.0",
            "author": {
                "displayName": "secret-user",
                "fullName": "Secret Name",
            },
        }

        summarized = _summarize_workout_upload_response(payload)

        self.assertEqual(summarized["workout_id"], 123)
        self.assertEqual(summarized["workout_name"], "Intervals")
        self.assertEqual(summarized["sport_type"], "running")
        self.assertNotIn("author", summarized)

    def test_schedule_summary_only_returns_safe_fields(self) -> None:
        payload = {
            "scheduledWorkoutId": 999,
            "date": "2026-03-28",
            "ownerId": 12345,
        }

        summarized = _summarize_schedule_response(payload)

        self.assertEqual(
            summarized,
            {
                "scheduled_workout_id": 999,
                "date": "2026-03-28",
            },
        )


if __name__ == "__main__":
    unittest.main()
