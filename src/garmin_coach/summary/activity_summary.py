"""Per-activity summary generation from Garmin raw activity payloads."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any
import unicodedata

from ..storage.raw_store import RawJsonStore
from ..utils.activities import extract_activity_start

def _read_json_if_exists(store: RawJsonStore, relative_path: str | Path) -> Any | None:
    try:
        return store.read_json(relative_path)
    except FileNotFoundError:
        return None


def _coerce_float(value: Any, *, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _activity_discipline(type_key: str | None) -> str:
    lowered = (type_key or "").lower()
    if any(token in lowered for token in ("swim", "open_water", "pool")):
        return "swim"
    if any(token in lowered for token in ("bike", "cycling", "biking", "mtb", "indoor_cycling")):
        return "bike"
    if any(token in lowered for token in ("run", "trail", "track")):
        return "run"
    if any(token in lowered for token in ("strength", "gym", "cardio")):
        return "strength"
    if "triathlon" in lowered:
        return "triathlon"
    return "other"


def _format_duration(seconds: Any) -> str | None:
    if seconds is None:
        return None
    try:
        total_seconds = int(float(seconds))
    except (TypeError, ValueError):
        return None
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _slugify(value: str | None, *, fallback: str = "activity") -> str:
    if not value:
        return fallback
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.strip().lower()).strip("-")
    return slug or fallback


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class ActivitySummaryBuilder:
    """Build concise, cleaned summaries for synced Garmin activities."""

    def __init__(self, raw_store: RawJsonStore, summary_store: RawJsonStore) -> None:
        self.raw_store = raw_store
        self.summary_store = summary_store

    def available_activity_ids(self) -> list[str]:
        activity_root = self.raw_store.base_dir / "activities" / "by_id"
        if not activity_root.exists():
            return []
        return sorted(
            path.name
            for path in activity_root.iterdir()
            if path.is_dir() and path.name.isdigit()
        )

    def _relative_activity_path(self, activity_id: str, filename: str) -> Path:
        return Path("activities/by_id") / str(activity_id) / filename

    def _summary_relative_path(
        self,
        *,
        activity_id: str,
        activity_date: str | None,
        start: datetime | None,
        activity_name: str | None,
    ) -> Path:
        date_part = activity_date or "unknown-date"
        time_part = start.strftime("%H-%M-%S") if start is not None else "unknown-time"
        slug = _slugify(activity_name)
        filename = f"{date_part}_{time_part}_{slug}_{activity_id}.json"
        return Path("activities/by_date") / filename

    def _split_summaries(self, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, dict):
            return []
        split_summaries = raw.get("splitSummaries")
        if not isinstance(split_summaries, list):
            return []
        cleaned: list[dict[str, Any]] = []
        for item in split_summaries:
            if not isinstance(item, dict):
                continue
            cleaned.append(
                {
                    "split_type": item.get("splitType"),
                    "distance_km": _coerce_float(
                        None if item.get("distance") is None else item.get("distance") / 1000.0,
                        digits=2,
                    ),
                    "duration_minutes": _coerce_float(
                        None if item.get("duration") is None else item.get("duration") / 60.0,
                        digits=2,
                    ),
                    "moving_minutes": _coerce_float(
                        None
                        if item.get("movingDuration") is None
                        else item.get("movingDuration") / 60.0,
                        digits=2,
                    ),
                    "average_hr": item.get("averageHR"),
                    "max_hr": item.get("maxHR"),
                    "average_speed_kmh": _coerce_float(
                        None
                        if item.get("averageSpeed") is None
                        else item.get("averageSpeed") * 3.6,
                        digits=2,
                    ),
                    "average_power": item.get("averagePower"),
                    "normalized_power": item.get("normalizedPower"),
                    "average_cadence": item.get("averageRunCadence")
                    or item.get("avgStepFrequency"),
                    "elevation_gain_m": item.get("elevationGain"),
                    "elevation_loss_m": item.get("elevationLoss"),
                }
            )
        return cleaned

    def build_activity_summary(self, activity_id: str) -> dict[str, Any]:
        list_entry = _read_json_if_exists(
            self.raw_store,
            self._relative_activity_path(activity_id, "list_entry.json"),
        )
        summary = _read_json_if_exists(
            self.raw_store,
            self._relative_activity_path(activity_id, "summary.json"),
        )
        details = _read_json_if_exists(
            self.raw_store,
            self._relative_activity_path(activity_id, "details.json"),
        )
        split_summaries = _read_json_if_exists(
            self.raw_store,
            self._relative_activity_path(activity_id, "split_summaries.json"),
        )

        if not isinstance(list_entry, dict) and not isinstance(summary, dict):
            raise FileNotFoundError(f"No raw activity data found for activity {activity_id}.")

        source = list_entry if isinstance(list_entry, dict) else summary
        summary_dto = summary.get("summaryDTO", {}) if isinstance(summary, dict) else {}
        start = extract_activity_start(source) or extract_activity_start(summary or {})
        type_key = None
        if isinstance(source, dict):
            activity_type = source.get("activityType") or source.get("activityTypeDTO")
            if isinstance(activity_type, dict):
                type_key = activity_type.get("typeKey")

        discipline = _activity_discipline(type_key)
        distance = source.get("distance") or summary_dto.get("distance")
        duration = source.get("duration") or summary_dto.get("duration")
        moving_duration = source.get("movingDuration") or summary_dto.get("movingDuration")
        average_speed = source.get("averageSpeed") or summary_dto.get("averageSpeed")

        pace_min_per_km = None
        if discipline == "run" and average_speed:
            try:
                meters_per_second = float(average_speed)
                if meters_per_second > 0:
                    pace_min_per_km = round(1000.0 / meters_per_second / 60.0, 2)
            except (TypeError, ValueError):
                pace_min_per_km = None

        detail_metrics = (
            details.get("activityDetailMetrics")
            if isinstance(details, dict)
            else None
        )
        detail_points = len(detail_metrics) if isinstance(detail_metrics, list) else 0

        payload = {
            "activity_id": str(source.get("activityId") or activity_id),
            "activity_name": source.get("activityName"),
            "activity_date": None if start is None else start.date().isoformat(),
            "activity_start_local": None if start is None else start.isoformat(),
            "calendar_date": None if start is None else start.date().isoformat(),
            "start_time": None if start is None else start.isoformat(),
            "discipline": discipline,
            "type_key": type_key,
            "overview": {
                "duration_minutes": _coerce_float(
                    None if duration is None else duration / 60.0,
                    digits=2,
                ),
                "moving_minutes": _coerce_float(
                    None if moving_duration is None else moving_duration / 60.0,
                    digits=2,
                ),
                "duration_hms": _format_duration(duration),
                "distance_km": _coerce_float(
                    None if distance is None else distance / 1000.0,
                    digits=2,
                ),
                "average_speed_kmh": _coerce_float(
                    None if average_speed is None else average_speed * 3.6,
                    digits=2,
                ),
                "pace_min_per_km": pace_min_per_km,
                "average_hr": source.get("averageHR") or summary_dto.get("averageHR"),
                "max_hr": source.get("maxHR") or summary_dto.get("maxHR"),
                "calories": source.get("calories") or summary_dto.get("calories"),
                "training_load": _coerce_float(
                    source.get("activityTrainingLoad")
                    or summary_dto.get("activityTrainingLoad"),
                    digits=1,
                ),
                "aerobic_training_effect": source.get("aerobicTrainingEffect")
                or summary_dto.get("trainingEffect"),
                "anaerobic_training_effect": source.get("anaerobicTrainingEffect")
                or summary_dto.get("anaerobicTrainingEffect"),
                "training_effect_label": source.get("trainingEffectLabel")
                or summary_dto.get("trainingEffectLabel"),
            },
            "sport_specific": {
                "cadence": source.get("averageRunningCadenceInStepsPerMinute")
                or source.get("averageSwimCadenceInStrokesPerMinute"),
                "power_avg": source.get("avgPower"),
                "power_normalized": source.get("normPower"),
                "stride_length_cm": _coerce_float(source.get("avgStrideLength"), digits=1),
                "elevation_gain_m": source.get("elevationGain"),
                "elevation_loss_m": source.get("elevationLoss"),
                "pool_length_m": _coerce_float(
                    None
                    if source.get("poolLength") is None
                    else source.get("poolLength") / 100.0,
                    digits=1,
                ),
                "active_lengths": source.get("activeLengths"),
                "strokes": source.get("strokes"),
                "swolf": source.get("averageSwolf"),
                "water_estimated_ml": source.get("waterEstimated"),
            },
            "split_summaries": self._split_summaries(split_summaries),
            "data_quality": {
                "detail_points": detail_points,
                "has_details": detail_points > 0,
                "has_split_summaries": bool(
                    isinstance(split_summaries, dict)
                    and split_summaries.get("splitSummaries")
                ),
            },
            "available_raw_files": [
                name
                for name in (
                    "list_entry.json",
                    "summary.json",
                    "details.json",
                    "split_summaries.json",
                    "splits.json",
                    "typed_splits.json",
                )
                if (
                    self.raw_store.base_dir
                    / self._relative_activity_path(activity_id, name)
                ).exists()
            ],
        }
        return payload

    def build_and_save_activity_summary(self, activity_id: str) -> dict[str, Any]:
        payload = self.build_activity_summary(activity_id)
        relative_path = self._summary_relative_path(
            activity_id=str(activity_id),
            activity_date=payload.get("activity_date"),
            start=_parse_iso_datetime(payload.get("activity_start_local")),
            activity_name=payload.get("activity_name"),
        )
        result = self.summary_store.save_json(
            relative_path,
            payload,
        )
        return {
            "activity_id": str(activity_id),
            "path": str(result.path),
            "changed": bool(result.changed),
        }

    def build_and_save_activity_summaries(
        self,
        *,
        activity_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        activity_ids = [activity_id] if activity_id is not None else self.available_activity_ids()
        if limit is not None and limit >= 0:
            activity_ids = activity_ids[:limit]

        saved: list[dict[str, Any]] = []
        for current_activity_id in activity_ids:
            saved.append(self.build_and_save_activity_summary(current_activity_id))

        return {
            "activity_count": len(saved),
            "items": saved,
        }
