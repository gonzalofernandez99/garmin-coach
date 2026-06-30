"""Tests for Garmin cycling workout generation."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from garmin_coach.config import Settings
from garmin_coach.workouts.cycling import (
    CyclingIntervalsSpec,
    CyclingWorkoutService,
    build_cycling_intervals_workout,
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


class CyclingWorkoutBuilderTest(unittest.TestCase):
    def test_builds_time_intervals_for_cycling(self) -> None:
        payload = build_cycling_intervals_workout(
            CyclingIntervalsSpec(
                name="Bike 5x4min",
                warmup_seconds=900,
                repeats=5,
                interval_seconds=240,
                recovery_seconds=120,
                cooldown_seconds=600,
                target="Z4",
            )
        )

        self.assertEqual(payload["workoutName"], "Bike 5x4min")
        self.assertEqual(payload["sportType"]["sportTypeKey"], "cycling")
        self.assertEqual(payload["sportType"]["sportTypeId"], 2)
        self.assertEqual(payload["estimatedDurationInSecs"], 3180)

        steps = payload["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(steps[0]["endCondition"]["conditionTypeKey"], "time")
        self.assertEqual(steps[0]["endConditionValue"], 900.0)

        repeat_group = steps[1]
        self.assertTrue(repeat_group["skipLastRestStep"])
        self.assertEqual(repeat_group["numberOfIterations"], 5)

        interval = repeat_group["workoutSteps"][0]
        self.assertEqual(interval["stepType"]["stepTypeKey"], "interval")
        self.assertEqual(interval["endCondition"]["conditionTypeKey"], "time")
        self.assertEqual(interval["endConditionValue"], 240.0)
        self.assertEqual(interval["targetType"]["workoutTargetTypeKey"], "no.target")
        self.assertIn("Objetivo: Z4", interval["description"])

        recovery = repeat_group["workoutSteps"][1]
        self.assertEqual(recovery["stepType"]["stepTypeKey"], "recovery")
        self.assertEqual(recovery["endConditionValue"], 120.0)

        cooldown = steps[2]
        self.assertEqual(cooldown["stepType"]["stepTypeKey"], "cooldown")
        self.assertEqual(cooldown["endConditionValue"], 600.0)
        self.assertNotIn("estimatedDistanceInMeters", payload)

    def test_builds_steady_block_and_step_specific_targets(self) -> None:
        payload = build_cycling_intervals_workout(
            CyclingIntervalsSpec(
                name="Bike 4x8min aerobic",
                warmup_seconds=900,
                repeats=4,
                interval_seconds=480,
                recovery_seconds=240,
                steady_seconds=1200,
                cooldown_seconds=600,
                warmup_target="Suave, RPE 3/10, cadencia 85-95 rpm",
                interval_target="Fuerte controlado, RPE 7/10, cadencia 85-95 rpm",
                recovery_target="Suave, RPE 3/10, recuperar bien",
                steady_target="Zona comoda/media, RPE 5/10, sin apretar",
                cooldown_target="Muy suave",
                skip_last_recovery=False,
            )
        )

        self.assertEqual(payload["estimatedDurationInSecs"], 5580)
        steps = payload["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(len(steps), 4)
        self.assertIn("RPE 3/10", steps[0]["description"])

        repeat_group = steps[1]
        self.assertFalse(repeat_group["skipLastRestStep"])
        self.assertEqual(repeat_group["numberOfIterations"], 4)
        self.assertIn(
            "Fuerte controlado",
            repeat_group["workoutSteps"][0]["description"],
        )
        self.assertIn("recuperar bien", repeat_group["workoutSteps"][1]["description"])

        steady = steps[2]
        self.assertEqual(steady["stepType"]["stepTypeKey"], "interval")
        self.assertEqual(steady["stepOrder"], 5)
        self.assertEqual(steady["endConditionValue"], 1200.0)
        self.assertIn("Zona comoda/media", steady["description"])

        cooldown = steps[3]
        self.assertEqual(cooldown["stepType"]["stepTypeKey"], "cooldown")
        self.assertEqual(cooldown["stepOrder"], 6)
        self.assertIn("Muy suave", cooldown["description"])

    def test_service_saves_workout_json(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            service = CyclingWorkoutService(settings)
            spec = service.parse_spec(
                name=None,
                warmup="15:00",
                repeats=5,
                interval_duration="4:00",
                recovery="2:00",
                cooldown="10:00",
                target="RPE 7/10",
                steady_duration="20:00",
                steady_target="RPE 5/10",
            )

            result = service.create_and_save(spec)

            saved_path = Path(result["saved_to"])
            self.assertTrue(saved_path.exists())
            self.assertIn("/workouts/cycling/", str(saved_path))
            payload = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["workoutName"], "Bike 5x4min")
            self.assertEqual(payload["sportType"]["sportTypeKey"], "cycling")
            self.assertEqual(len(payload["workoutSegments"][0]["workoutSteps"]), 4)


if __name__ == "__main__":
    unittest.main()
