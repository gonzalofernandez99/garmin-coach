"""Running workout builders compatible with Garmin Connect workout upload."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any
import unicodedata

from ..config import Settings
from ..storage.raw_store import RawJsonStore

RUNNING_SPORT = {
    "sportTypeId": 1,
    "sportTypeKey": "running",
    "displayOrder": 1,
}

METER_UNIT = {
    "unitId": 1,
    "unitKey": "meter",
    "factor": 100.0,
}

STEP_TYPE_WARMUP = {
    "stepTypeId": 1,
    "stepTypeKey": "warmup",
    "displayOrder": 1,
}

STEP_TYPE_COOLDOWN = {
    "stepTypeId": 2,
    "stepTypeKey": "cooldown",
    "displayOrder": 2,
}

STEP_TYPE_INTERVAL = {
    "stepTypeId": 3,
    "stepTypeKey": "interval",
    "displayOrder": 3,
}

STEP_TYPE_RECOVERY = {
    "stepTypeId": 4,
    "stepTypeKey": "recovery",
    "displayOrder": 4,
}

STEP_TYPE_REPEAT = {
    "stepTypeId": 6,
    "stepTypeKey": "repeat",
    "displayOrder": 6,
}

CONDITION_LAP_BUTTON = {
    "conditionTypeId": 1,
    "conditionTypeKey": "lap.button",
    "displayOrder": 1,
    "displayable": True,
}

CONDITION_TIME = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
    "displayable": True,
}

CONDITION_DISTANCE = {
    "conditionTypeId": 3,
    "conditionTypeKey": "distance",
    "displayOrder": 3,
    "displayable": True,
}

CONDITION_ITERATIONS = {
    "conditionTypeId": 7,
    "conditionTypeKey": "iterations",
    "displayOrder": 7,
    "displayable": False,
}

TARGET_NO = {
    "workoutTargetTypeId": 1,
    "workoutTargetTypeKey": "no.target",
    "displayOrder": 1,
}

TARGET_PACE_ZONE = {
    "workoutTargetTypeId": 6,
    "workoutTargetTypeKey": "pace.zone",
    "displayOrder": 6,
}


def _slugify(value: str | None, *, fallback: str = "workout") -> str:
    if not value:
        return fallback
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.strip().lower()).strip("-")
    return slug or fallback


def _parse_pace_seconds_per_km(value: str) -> int:
    cleaned = value.strip()
    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})|(\d{1,2}):(\d{2})", cleaned)
    if match:
        if match.group(4) is not None:
            minutes = int(match.group(4))
            seconds = int(match.group(5))
            return minutes * 60 + seconds
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(
        "Invalid pace format. Use MM:SS per km, for example 5:15 or 05:25."
    )


def _parse_duration_seconds(value: str) -> int:
    cleaned = value.strip()
    if ":" in cleaned:
        parts = [int(piece) for piece in cleaned.split(":")]
        if len(parts) == 2:
            minutes, seconds = parts
            return minutes * 60 + seconds
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return hours * 3600 + minutes * 60 + seconds
        raise ValueError(
            "Invalid duration format. Use MM:SS, HH:MM:SS or a number of minutes."
        )
    try:
        minutes = float(cleaned)
    except ValueError as exc:
        raise ValueError(
            "Invalid duration format. Use MM:SS, HH:MM:SS or a number of minutes."
        ) from exc
    return int(round(minutes * 60))


def _parse_pace_range(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"\s*([0-9]{1,2}:[0-9]{2})\s*[-–]\s*([0-9]{1,2}:[0-9]{2})\s*", value)
    if not match:
        raise ValueError(
            "Invalid pace range. Use MM:SS-MM:SS, for example 5:15-5:25."
        )
    first = match.group(1)
    second = match.group(2)
    return first, second


def _speed_mps_from_pace_seconds(seconds_per_km: int) -> float:
    return round(1000.0 / float(seconds_per_km), 7)


def _pace_target_values(fast_or_first: str, slow_or_second: str) -> tuple[float, float]:
    pace_a = _parse_pace_seconds_per_km(fast_or_first)
    pace_b = _parse_pace_seconds_per_km(slow_or_second)
    fastest = min(pace_a, pace_b)
    slowest = max(pace_a, pace_b)
    return (
        _speed_mps_from_pace_seconds(fastest),
        _speed_mps_from_pace_seconds(slowest),
    )


def _step_base(
    *,
    step_order: int,
    step_type: dict[str, Any],
    description: str,
    target_type: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": step_type,
        "description": description,
        "targetType": target_type,
    }


def _distance_step(
    *,
    step_order: int,
    step_type: dict[str, Any],
    distance_m: float,
    description: str,
    target_type: dict[str, Any],
    target_value_one: float | None = None,
    target_value_two: float | None = None,
    category: str | None = None,
    exercise_name: str | None = None,
) -> dict[str, Any]:
    payload = _step_base(
        step_order=step_order,
        step_type=step_type,
        description=description,
        target_type=target_type,
    )
    payload.update(
        {
            "endCondition": CONDITION_DISTANCE,
            "endConditionValue": float(distance_m),
            "preferredEndConditionUnit": METER_UNIT,
        }
    )
    if target_value_one is not None:
        payload["targetValueOne"] = target_value_one
    if target_value_two is not None:
        payload["targetValueTwo"] = target_value_two
    if category is not None:
        payload["category"] = category
    if exercise_name is not None:
        payload["exerciseName"] = exercise_name
    return payload


def _time_step(
    *,
    step_order: int,
    step_type: dict[str, Any],
    duration_seconds: int,
    description: str,
    target_type: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _step_base(
        step_order=step_order,
        step_type=step_type,
        description=description,
        target_type=target_type or TARGET_NO,
    )
    payload.update(
        {
            "endCondition": CONDITION_TIME,
            "endConditionValue": float(duration_seconds),
        }
    )
    return payload


def _lap_button_step(
    *,
    step_order: int,
    step_type: dict[str, Any],
    description: str,
) -> dict[str, Any]:
    payload = _step_base(
        step_order=step_order,
        step_type=step_type,
        description=description,
        target_type=TARGET_NO,
    )
    payload.update(
        {
            "endCondition": CONDITION_LAP_BUTTON,
            "endConditionValue": None,
        }
    )
    return payload


def _parse_distance_or_range_km(value: str) -> tuple[float | None, float | None]:
    cleaned = value.strip()
    if "-" in cleaned or "–" in cleaned:
        separator = "-" if "-" in cleaned else "–"
        left, right = [part.strip() for part in cleaned.split(separator, maxsplit=1)]
        return float(left), float(right)
    exact = float(cleaned)
    return exact, exact


@dataclass(frozen=True, slots=True)
class RunningIntervalsSpec:
    """User-facing configuration for a Garmin running interval workout."""

    name: str
    warmup_km: float
    repeats: int
    interval_m: int
    pace_fast: str
    pace_slow: str
    recovery_seconds: int
    cooldown_km_min: float
    cooldown_km_max: float
    description: str | None = None
    easy_pace_for_estimate: str = "6:30"

    @property
    def cooldown_is_range(self) -> bool:
        return self.cooldown_km_min != self.cooldown_km_max

    @property
    def total_distance_m(self) -> float | None:
        if self.cooldown_is_range:
            return None
        return round(
            (self.warmup_km + self.cooldown_km_max) * 1000.0
            + self.repeats * self.interval_m,
            1,
        )

    @property
    def estimated_duration_secs(self) -> int | None:
        if self.cooldown_is_range:
            return None
        easy_pace = _parse_pace_seconds_per_km(self.easy_pace_for_estimate)
        interval_fast = _parse_pace_seconds_per_km(self.pace_fast)
        interval_slow = _parse_pace_seconds_per_km(self.pace_slow)
        interval_avg = (interval_fast + interval_slow) / 2.0
        warmup = self.warmup_km * easy_pace
        work = self.repeats * (self.interval_m / 1000.0) * interval_avg
        recovery = max(self.repeats - 1, 0) * self.recovery_seconds
        cooldown = self.cooldown_km_max * easy_pace
        return int(round(warmup + work + recovery + cooldown))


def build_running_intervals_workout(spec: RunningIntervalsSpec) -> dict[str, Any]:
    """Build a Garmin Connect workout payload for a running interval session."""

    if spec.repeats < 1:
        raise ValueError("repeats must be >= 1")
    if spec.interval_m < 100:
        raise ValueError("interval_m must be >= 100")
    if spec.warmup_km <= 0:
        raise ValueError("warmup_km must be > 0")
    if spec.cooldown_km_min <= 0 or spec.cooldown_km_max <= 0:
        raise ValueError("cooldown_km must be > 0")

    target_fast, target_slow = _pace_target_values(spec.pace_fast, spec.pace_slow)

    warmup = _distance_step(
        step_order=1,
        step_type=STEP_TYPE_WARMUP,
        distance_m=spec.warmup_km * 1000.0,
        description=f"Calentamiento suave {spec.warmup_km:g} km.",
        target_type=TARGET_NO,
    )
    interval = _distance_step(
        step_order=3,
        step_type=STEP_TYPE_INTERVAL,
        distance_m=float(spec.interval_m),
        description=(
            f"{spec.interval_m} m al ritmo objetivo "
            f"{spec.pace_fast}-{spec.pace_slow} min/km."
        ),
        target_type=TARGET_PACE_ZONE,
        target_value_one=target_fast,
        target_value_two=target_slow,
        category="RUN",
        exercise_name="RUN",
    )
    recovery = _time_step(
        step_order=4,
        step_type=STEP_TYPE_RECOVERY,
        duration_seconds=spec.recovery_seconds,
        description="Recuperacion caminando o trote suave.",
    )
    repeat_group = {
        "type": "RepeatGroupDTO",
        "stepOrder": 2,
        "stepType": STEP_TYPE_REPEAT,
        "childStepId": 1,
        "numberOfIterations": spec.repeats,
        "workoutSteps": [interval, recovery],
        "endCondition": CONDITION_ITERATIONS,
        "endConditionValue": float(spec.repeats),
        "skipLastRestStep": True,
        "smartRepeat": False,
    }
    if spec.cooldown_is_range:
        cooldown_description = (
            f"Enfriar suave {spec.cooldown_km_min:g}-{spec.cooldown_km_max:g} km."
        )
        cooldown = _lap_button_step(
            step_order=5,
            step_type=STEP_TYPE_COOLDOWN,
            description=cooldown_description,
        )
    else:
        cooldown = _distance_step(
            step_order=5,
            step_type=STEP_TYPE_COOLDOWN,
            distance_m=spec.cooldown_km_max * 1000.0,
            description=f"Enfriar suave {spec.cooldown_km_max:g} km.",
            target_type=TARGET_NO,
        )

    payload: dict[str, Any] = {
        "workoutName": spec.name,
        "description": spec.description
        or (
            f"Calentamiento {spec.warmup_km:g} km, "
            f"{spec.repeats} x {spec.interval_m} m a {spec.pace_fast}-{spec.pace_slow}, "
            f"recuperacion {spec.recovery_seconds}s, "
            f"enfriar {spec.cooldown_km_min:g}"
            + (
                f"-{spec.cooldown_km_max:g}"
                if spec.cooldown_is_range
                else ""
            )
            + " km."
        ),
        "sportType": RUNNING_SPORT,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": RUNNING_SPORT,
                "workoutSteps": [warmup, repeat_group, cooldown],
            }
        ],
    }
    if spec.estimated_duration_secs is not None:
        payload["estimatedDurationInSecs"] = spec.estimated_duration_secs
    if spec.total_distance_m is not None:
        payload["estimatedDistanceInMeters"] = spec.total_distance_m
    return payload


class RunningWorkoutService:
    """Create and persist Garmin-compatible running workout payloads."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.summary_store = RawJsonStore(settings.summaries_dir)

    def parse_spec(
        self,
        *,
        name: str | None,
        warmup_km: float,
        repeats: int,
        interval_m: int,
        pace_range: str,
        recovery: str,
        cooldown_km: str,
        description: str | None = None,
    ) -> RunningIntervalsSpec:
        pace_fast, pace_slow = _parse_pace_range(pace_range)
        cooldown_min, cooldown_max = _parse_distance_or_range_km(cooldown_km)
        return RunningIntervalsSpec(
            name=name or f"Run {repeats}x{interval_m}m {pace_fast}-{pace_slow}",
            warmup_km=warmup_km,
            repeats=repeats,
            interval_m=interval_m,
            pace_fast=pace_fast,
            pace_slow=pace_slow,
            recovery_seconds=_parse_duration_seconds(recovery),
            cooldown_km_min=float(cooldown_min),
            cooldown_km_max=float(cooldown_max),
            description=description,
        )

    def _relative_path(self, workout_name: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        slug = _slugify(workout_name)
        return Path("workouts/running") / f"{timestamp}_{slug}.json"

    def create_and_save(self, spec: RunningIntervalsSpec) -> dict[str, Any]:
        payload = build_running_intervals_workout(spec)
        save_result = self.summary_store.save_json(self._relative_path(spec.name), payload)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "workout_name": spec.name,
            "saved_to": str(save_result.path),
            "changed": save_result.changed,
            "sha256": save_result.sha256,
            "spec": {
                "warmup_km": spec.warmup_km,
                "repeats": spec.repeats,
                "interval_m": spec.interval_m,
                "pace_fast": spec.pace_fast,
                "pace_slow": spec.pace_slow,
                "recovery_seconds": spec.recovery_seconds,
                "cooldown_km_min": spec.cooldown_km_min,
                "cooldown_km_max": spec.cooldown_km_max,
            },
            "workout_payload": payload,
        }
