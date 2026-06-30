"""Cycling workout builders compatible with Garmin Connect workout upload."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any
import unicodedata

from ..config import Settings
from ..storage.raw_store import RawJsonStore

CYCLING_SPORT = {
    "sportTypeId": 2,
    "sportTypeKey": "cycling",
    "displayOrder": 2,
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

CONDITION_TIME = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
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


def _slugify(value: str | None, *, fallback: str = "workout") -> str:
    if not value:
        return fallback
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.strip().lower()).strip("-")
    return slug or fallback


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


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes:g}min" if remainder == 0 else f"{minutes}m{remainder}s"
    hours, minutes = divmod(minutes, 60)
    if minutes == 0 and remainder == 0:
        return f"{hours}h"
    if remainder == 0:
        return f"{hours}h{minutes}min"
    return f"{hours}h{minutes}m{remainder}s"


def _step_base(
    *,
    step_order: int,
    step_type: dict[str, Any],
    description: str,
) -> dict[str, Any]:
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": step_type,
        "description": description,
        "targetType": TARGET_NO,
    }


def _time_step(
    *,
    step_order: int,
    step_type: dict[str, Any],
    duration_seconds: int,
    description: str,
) -> dict[str, Any]:
    payload = _step_base(
        step_order=step_order,
        step_type=step_type,
        description=description,
    )
    payload.update(
        {
            "endCondition": CONDITION_TIME,
            "endConditionValue": float(duration_seconds),
        }
    )
    return payload


def _with_target(description: str, target: str | None) -> str:
    if not target:
        return description
    return f"{description} Objetivo: {target}."


@dataclass(frozen=True, slots=True)
class CyclingIntervalsSpec:
    """User-facing configuration for a Garmin cycling interval workout."""

    name: str
    warmup_seconds: int
    repeats: int
    interval_seconds: int
    recovery_seconds: int
    cooldown_seconds: int
    target: str | None = None
    warmup_target: str | None = None
    interval_target: str | None = None
    recovery_target: str | None = None
    steady_seconds: int = 0
    steady_target: str | None = None
    cooldown_target: str | None = None
    skip_last_recovery: bool = True
    description: str | None = None

    @property
    def effective_interval_target(self) -> str | None:
        return self.interval_target or self.target

    @property
    def estimated_duration_secs(self) -> int:
        recovery_repeats = (
            max(self.repeats - 1, 0)
            if self.skip_last_recovery
            else self.repeats
        )
        return (
            self.warmup_seconds
            + self.repeats * self.interval_seconds
            + recovery_repeats * self.recovery_seconds
            + self.steady_seconds
            + self.cooldown_seconds
        )


def build_cycling_intervals_workout(spec: CyclingIntervalsSpec) -> dict[str, Any]:
    """Build a Garmin Connect workout payload for a cycling interval session."""

    if spec.repeats < 1:
        raise ValueError("repeats must be >= 1")
    if spec.warmup_seconds <= 0:
        raise ValueError("warmup must be > 0")
    if spec.interval_seconds <= 0:
        raise ValueError("interval_duration must be > 0")
    if spec.recovery_seconds <= 0:
        raise ValueError("recovery must be > 0")
    if spec.cooldown_seconds <= 0:
        raise ValueError("cooldown must be > 0")
    if spec.steady_seconds < 0:
        raise ValueError("steady_duration must be >= 0")
    if spec.steady_seconds == 0 and spec.steady_target:
        raise ValueError("steady_target requires steady_duration")

    interval_label = _format_duration(spec.interval_seconds)

    warmup = _time_step(
        step_order=1,
        step_type=STEP_TYPE_WARMUP,
        duration_seconds=spec.warmup_seconds,
        description=_with_target(
            f"Calentamiento suave {_format_duration(spec.warmup_seconds)}.",
            spec.warmup_target,
        ),
    )
    interval = _time_step(
        step_order=3,
        step_type=STEP_TYPE_INTERVAL,
        duration_seconds=spec.interval_seconds,
        description=_with_target(
            f"{interval_label} fuerte en bici.",
            spec.effective_interval_target,
        ),
    )
    recovery = _time_step(
        step_order=4,
        step_type=STEP_TYPE_RECOVERY,
        duration_seconds=spec.recovery_seconds,
        description=_with_target("Recuperacion muy suave.", spec.recovery_target),
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
        "skipLastRestStep": spec.skip_last_recovery,
        "smartRepeat": False,
    }
    workout_steps = [warmup, repeat_group]
    cooldown_order = 5
    if spec.steady_seconds > 0:
        workout_steps.append(
            _time_step(
                step_order=5,
                step_type=STEP_TYPE_INTERVAL,
                duration_seconds=spec.steady_seconds,
                description=_with_target(
                    f"Aerobico constante {_format_duration(spec.steady_seconds)}.",
                    spec.steady_target,
                ),
            )
        )
        cooldown_order = 6
    cooldown = _time_step(
        step_order=cooldown_order,
        step_type=STEP_TYPE_COOLDOWN,
        duration_seconds=spec.cooldown_seconds,
        description=_with_target(
            f"Enfriar suave {_format_duration(spec.cooldown_seconds)}.",
            spec.cooldown_target,
        ),
    )
    workout_steps.append(cooldown)

    target_description = (
        f", objetivo {spec.effective_interval_target}"
        if spec.effective_interval_target
        else ""
    )
    steady_description = (
        f", aerobico {_format_duration(spec.steady_seconds)}"
        + (f" objetivo {spec.steady_target}" if spec.steady_target else "")
        if spec.steady_seconds > 0
        else ""
    )
    recovery_count = (
        spec.repeats
        if not spec.skip_last_recovery
        else max(spec.repeats - 1, 0)
    )
    payload: dict[str, Any] = {
        "workoutName": spec.name,
        "description": spec.description
        or (
            f"Calentamiento {_format_duration(spec.warmup_seconds)}, "
            f"{spec.repeats} x {_format_duration(spec.interval_seconds)}"
            f"{target_description}, "
            f"{recovery_count} recuperaciones de "
            f"{_format_duration(spec.recovery_seconds)}"
            f"{steady_description}, "
            f"enfriar {_format_duration(spec.cooldown_seconds)}."
        ),
        "sportType": CYCLING_SPORT,
        "estimatedDurationInSecs": spec.estimated_duration_secs,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": CYCLING_SPORT,
                "workoutSteps": workout_steps,
            }
        ],
    }
    return payload


class CyclingWorkoutService:
    """Create and persist Garmin-compatible cycling workout payloads."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.summary_store = RawJsonStore(settings.summaries_dir)

    def parse_spec(
        self,
        *,
        name: str | None,
        warmup: str,
        repeats: int,
        interval_duration: str,
        recovery: str,
        cooldown: str,
        target: str | None = None,
        warmup_target: str | None = None,
        interval_target: str | None = None,
        recovery_target: str | None = None,
        steady_duration: str | None = None,
        steady_target: str | None = None,
        cooldown_target: str | None = None,
        skip_last_recovery: bool = True,
        description: str | None = None,
    ) -> CyclingIntervalsSpec:
        interval_seconds = _parse_duration_seconds(interval_duration)
        steady_seconds = (
            _parse_duration_seconds(steady_duration)
            if steady_duration is not None
            else 0
        )
        return CyclingIntervalsSpec(
            name=name or f"Bike {repeats}x{_format_duration(interval_seconds)}",
            warmup_seconds=_parse_duration_seconds(warmup),
            repeats=repeats,
            interval_seconds=interval_seconds,
            recovery_seconds=_parse_duration_seconds(recovery),
            cooldown_seconds=_parse_duration_seconds(cooldown),
            target=target,
            warmup_target=warmup_target,
            interval_target=interval_target,
            recovery_target=recovery_target,
            steady_seconds=steady_seconds,
            steady_target=steady_target,
            cooldown_target=cooldown_target,
            skip_last_recovery=skip_last_recovery,
            description=description,
        )

    def _relative_path(self, workout_name: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        slug = _slugify(workout_name)
        return Path("workouts/cycling") / f"{timestamp}_{slug}.json"

    def create_and_save(self, spec: CyclingIntervalsSpec) -> dict[str, Any]:
        payload = build_cycling_intervals_workout(spec)
        save_result = self.summary_store.save_json(self._relative_path(spec.name), payload)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "workout_name": spec.name,
            "saved_to": str(save_result.path),
            "changed": save_result.changed,
            "sha256": save_result.sha256,
            "spec": {
                "warmup_seconds": spec.warmup_seconds,
                "repeats": spec.repeats,
                "interval_seconds": spec.interval_seconds,
                "recovery_seconds": spec.recovery_seconds,
                "steady_seconds": spec.steady_seconds,
                "cooldown_seconds": spec.cooldown_seconds,
                "target": spec.target,
                "warmup_target": spec.warmup_target,
                "interval_target": spec.interval_target,
                "recovery_target": spec.recovery_target,
                "steady_target": spec.steady_target,
                "cooldown_target": spec.cooldown_target,
                "skip_last_recovery": spec.skip_last_recovery,
            },
            "workout_payload": payload,
        }
