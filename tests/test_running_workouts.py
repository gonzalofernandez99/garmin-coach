"""Tests for Garmin running workout generation."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from garmin_coach.config import Settings
from garmin_coach.workouts.running import (
    RunningIntervalsSpec,
    RunningWorkoutService,
    build_running_intervals_workout,
)


def _build_settings(root: Path) -> Settings:
    data_dir = root / "data"
    return Settings(
        project_root=root,
        env_file=root / ".env",
        email="user@example.com",
        password="secret",
        tokenstore_path=root / ".secrets" / "garmin_tokens",
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        normalized_dir=data_dir / "normalized",
        summaries_dir=data_dir / "summaries",
        logs_dir=data_dir / "logs",
        sqlite_path=data_dir / "state" / "garmin_coach.db",
        region="global",
        log_level="INFO",
        retries=1,
        retry_backoff_seconds=0.0,
    )


class RunningWorkoutBuilderTest(unittest.TestCase):
    def test_builds_distance_intervals_with_pace_targets(self) -> None:
        payload = build_running_intervals_workout(
            RunningIntervalsSpec(
                name="Run 5x1000m 5:15-5:25",
                warmup_km=2.0,
                repeats=5,
                interval_m=1000,
                pace_fast="5:15",
                pace_slow="5:25",
                recovery_seconds=120,
                cooldown_km_min=1.0,
                cooldown_km_max=2.0,
            )
        )

        self.assertEqual(payload["workoutName"], "Run 5x1000m 5:15-5:25")
        steps = payload["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(steps[0]["endCondition"]["conditionTypeKey"], "distance")
        self.assertEqual(steps[0]["endConditionValue"], 2000.0)

        repeat_group = steps[1]
        self.assertTrue(repeat_group["skipLastRestStep"])
        self.assertEqual(repeat_group["numberOfIterations"], 5)

        interval = repeat_group["workoutSteps"][0]
        self.assertEqual(interval["endCondition"]["conditionTypeKey"], "distance")
        self.assertEqual(interval["endConditionValue"], 1000.0)
        self.assertEqual(interval["targetType"]["workoutTargetTypeKey"], "pace.zone")
        self.assertAlmostEqual(interval["targetValueOne"], 3.1746032)
        self.assertAlmostEqual(interval["targetValueTwo"], 3.0769231)
        self.assertGreater(interval["targetValueOne"], interval["targetValueTwo"])

        recovery = repeat_group["workoutSteps"][1]
        self.assertEqual(recovery["endCondition"]["conditionTypeKey"], "time")
        self.assertEqual(recovery["endConditionValue"], 120.0)

        cooldown = steps[2]
        self.assertEqual(cooldown["endCondition"]["conditionTypeKey"], "lap.button")
        self.assertNotIn("estimatedDistanceInMeters", payload)
        self.assertNotIn("estimatedDurationInSecs", payload)

    def test_builds_exact_cooldown_with_estimates(self) -> None:
        payload = build_running_intervals_workout(
            RunningIntervalsSpec(
                name="Run 5x1000m exact",
                warmup_km=2.0,
                repeats=5,
                interval_m=1000,
                pace_fast="5:15",
                pace_slow="5:25",
                recovery_seconds=120,
                cooldown_km_min=1.0,
                cooldown_km_max=1.0,
            )
        )

        self.assertEqual(payload["estimatedDistanceInMeters"], 8000.0)
        self.assertGreater(payload["estimatedDurationInSecs"], 0)
        cooldown = payload["workoutSegments"][0]["workoutSteps"][2]
        self.assertEqual(cooldown["endCondition"]["conditionTypeKey"], "distance")
        self.assertEqual(cooldown["endConditionValue"], 1000.0)

    def test_service_saves_workout_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            service = RunningWorkoutService(settings)
            spec = service.parse_spec(
                name=None,
                warmup_km=2.0,
                repeats=5,
                interval_m=1000,
                pace_range="5:15-5:25",
                recovery="2:00",
                cooldown_km="1-2",
            )

            result = service.create_and_save(spec)

            saved_path = Path(result["saved_to"])
            self.assertTrue(saved_path.exists())
            payload = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["workoutName"], "Run 5x1000m 5:15-5:25")


if __name__ == "__main__":
    unittest.main()
