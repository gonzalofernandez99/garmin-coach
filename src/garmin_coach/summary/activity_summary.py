"""Per-activity summary generation from Garmin raw activity payloads."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any
import unicodedata

from ..storage.raw_store import RawJsonStore
from ..utils.activities import extract_activity_start
from ..utils.dates import parse_iso_date

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


def _format_duration_rounded(seconds: Any) -> str | None:
    if seconds is None:
        return None
    try:
        total_seconds = int(round(float(seconds)))
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


def _pace_seconds(duration_seconds: Any, distance_meters: Any, *, per_meters: float) -> float | None:
    try:
        duration_value = float(duration_seconds)
        distance_value = float(distance_meters)
    except (TypeError, ValueError):
        return None
    if duration_value <= 0 or distance_value <= 0:
        return None
    return duration_value / distance_value * per_meters


def _speed_kmh(distance_meters: Any, duration_seconds: Any, *, fallback_speed: Any = None) -> float | None:
    if fallback_speed is not None:
        try:
            speed_value = float(fallback_speed)
            if speed_value > 0:
                return round(speed_value * 3.6, 2)
        except (TypeError, ValueError):
            pass
    try:
        duration_value = float(duration_seconds)
        distance_value = float(distance_meters)
    except (TypeError, ValueError):
        return None
    if duration_value <= 0 or distance_value < 0:
        return None
    return round(distance_value / duration_value * 3.6, 2)


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

    def _activity_source(self, activity_id: str) -> dict[str, Any] | None:
        list_entry = _read_json_if_exists(
            self.raw_store,
            self._relative_activity_path(activity_id, "list_entry.json"),
        )
        if isinstance(list_entry, dict):
            return list_entry

        summary = _read_json_if_exists(
            self.raw_store,
            self._relative_activity_path(activity_id, "summary.json"),
        )
        if isinstance(summary, dict):
            return summary

        return None

    def _activity_calendar_date(self, activity_id: str) -> str | None:
        source = self._activity_source(activity_id)
        if not isinstance(source, dict):
            return None

        for field in ("activityDate", "calendarDate"):
            value = source.get(field)
            if isinstance(value, str) and len(value) >= 10:
                return value[:10]

        summary_dto = source.get("summaryDTO")
        if isinstance(summary_dto, dict):
            for field in ("activityDate", "calendarDate"):
                value = summary_dto.get(field)
                if isinstance(value, str) and len(value) >= 10:
                    return value[:10]

        start = extract_activity_start(source)
        if start is not None:
            return start.date().isoformat()
        return None

    def _normalize_date_range(
        self,
        *,
        start_date: str | None,
        end_date: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_start = (
            None if start_date is None else parse_iso_date(start_date).isoformat()
        )
        normalized_end = (
            None if end_date is None else parse_iso_date(end_date).isoformat()
        )
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise ValueError("start_date cannot be after end_date")
        return normalized_start, normalized_end

    def _filter_activity_ids_by_date(
        self,
        activity_ids: list[str],
        *,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]:
        normalized_start, normalized_end = self._normalize_date_range(
            start_date=start_date,
            end_date=end_date,
        )
        if normalized_start is None and normalized_end is None:
            return activity_ids

        filtered: list[str] = []
        for activity_id in activity_ids:
            activity_date = self._activity_calendar_date(activity_id)
            if activity_date is None:
                continue
            if normalized_start is not None and activity_date < normalized_start:
                continue
            if normalized_end is not None and activity_date > normalized_end:
                continue
            filtered.append(activity_id)
        return filtered

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

    def _running_segment(self, lap: dict[str, Any], index: int) -> dict[str, Any]:
        distance_m = lap.get("distance")
        duration_s = lap.get("duration")
        pace_seconds_per_km = _pace_seconds(duration_s, distance_m, per_meters=1000.0)
        distance_km = _coerce_float(
            None if distance_m is None else float(distance_m) / 1000.0,
            digits=2,
        )
        label = (
            f"km {index}"
            if distance_km is not None and 0.95 <= distance_km <= 1.05
            else f"lap {index}"
        )
        pace_display = _format_duration_rounded(pace_seconds_per_km)
        average_hr = lap.get("averageHR")

        return {
            "segment_index": index,
            "segment_type": "kilometer" if label.startswith("km ") else "lap",
            "label": label,
            "distance_m": _coerce_float(distance_m, digits=1),
            "distance_km": distance_km,
            "duration_seconds": _coerce_float(duration_s, digits=1),
            "duration_hms": _format_duration(duration_s),
            "pace_min_per_km": _coerce_float(
                None if pace_seconds_per_km is None else pace_seconds_per_km / 60.0,
                digits=2,
            ),
            "pace_per_km_display": None if pace_display is None else f"{pace_display}/km",
            "average_hr": average_hr,
            "max_hr": lap.get("maxHR"),
            "average_speed_kmh": _speed_kmh(
                distance_m,
                duration_s,
                fallback_speed=lap.get("averageSpeed"),
            ),
            "average_cadence_spm": _coerce_float(lap.get("averageRunCadence"), digits=1),
            "average_power": lap.get("averagePower"),
            "normalized_power": lap.get("normalizedPower"),
            "summary_line": (
                None
                if pace_display is None and average_hr is None
                else f"{label}: {pace_display or '-'}"
                f"{'/km' if pace_display is not None else ''}, {average_hr or '-'} ppm"
            ),
        }

    def _swim_segment(self, lap: dict[str, Any], index: int) -> dict[str, Any]:
        distance_m = lap.get("distance")
        duration_s = lap.get("duration")
        pace_seconds_per_100m = _pace_seconds(duration_s, distance_m, per_meters=100.0)
        pace_display = _format_duration_rounded(pace_seconds_per_100m)
        average_hr = lap.get("averageHR")
        is_rest = bool((distance_m or 0) == 0)
        label = f"lap {index}"
        length_dtos = lap.get("lengthDTOs")

        return {
            "segment_index": index,
            "segment_type": "rest" if is_rest else "lap",
            "label": label,
            "distance_m": _coerce_float(distance_m, digits=1),
            "distance_km": _coerce_float(
                None if distance_m is None else float(distance_m) / 1000.0,
                digits=3,
            ),
            "duration_seconds": _coerce_float(duration_s, digits=1),
            "duration_hms": _format_duration(duration_s),
            "pace_per_100m_seconds": _coerce_float(pace_seconds_per_100m, digits=1),
            "pace_per_100m_display": (
                None if pace_display is None else f"{pace_display}/100m"
            ),
            "average_hr": average_hr,
            "max_hr": lap.get("maxHR"),
            "average_speed_kmh": _speed_kmh(
                distance_m,
                duration_s,
                fallback_speed=lap.get("averageSpeed"),
            ),
            "average_swim_cadence_spm": _coerce_float(
                lap.get("averageSwimCadence"),
                digits=1,
            ),
            "average_swolf": lap.get("averageSWOLF"),
            "average_strokes": _coerce_float(lap.get("averageStrokes"), digits=1),
            "length_count": len(length_dtos) if isinstance(length_dtos, list) else 0,
            "is_rest": is_rest,
            "summary_line": (
                f"{label}: descanso, {average_hr or '-'} ppm"
                if is_rest
                else f"{label}: {int(distance_m or 0)} m, {pace_display or '-'}"
                f"{'/100m' if pace_display is not None else ''}, {average_hr or '-'} ppm"
            ),
        }

    def _bike_segment(self, lap: dict[str, Any], index: int) -> dict[str, Any]:
        distance_m = lap.get("distance")
        duration_s = lap.get("duration")
        average_hr = lap.get("averageHR")
        average_speed_kmh = _speed_kmh(
            distance_m,
            duration_s,
            fallback_speed=lap.get("averageSpeed"),
        )

        return {
            "segment_index": index,
            "segment_type": "lap",
            "label": f"lap {index}",
            "distance_m": _coerce_float(distance_m, digits=1),
            "distance_km": _coerce_float(
                None if distance_m is None else float(distance_m) / 1000.0,
                digits=2,
            ),
            "duration_seconds": _coerce_float(duration_s, digits=1),
            "duration_hms": _format_duration(duration_s),
            "average_hr": average_hr,
            "max_hr": lap.get("maxHR"),
            "average_speed_kmh": average_speed_kmh,
            "average_power": lap.get("averagePower"),
            "normalized_power": lap.get("normalizedPower"),
            "average_cadence_rpm": _coerce_float(
                lap.get("averageBikeCadence"),
                digits=1,
            ),
            "elevation_gain_m": lap.get("elevationGain"),
            "elevation_loss_m": lap.get("elevationLoss"),
            "summary_line": (
                f"lap {index}: "
                f"{_coerce_float(None if distance_m is None else float(distance_m) / 1000.0, digits=2) or '-'} km, "
                f"{average_speed_kmh or '-'} km/h, {average_hr or '-'} ppm"
            ),
        }

    def _segment_breakdown(self, raw: Any, *, discipline: str) -> list[dict[str, Any]]:
        if not isinstance(raw, dict):
            return []
        lap_dtos = raw.get("lapDTOs")
        if not isinstance(lap_dtos, list):
            return []

        cleaned: list[dict[str, Any]] = []
        for index, lap in enumerate(lap_dtos, start=1):
            if not isinstance(lap, dict):
                continue
            if discipline == "run":
                cleaned.append(self._running_segment(lap, index))
                continue
            if discipline == "swim":
                cleaned.append(self._swim_segment(lap, index))
                continue
            if discipline == "bike":
                cleaned.append(self._bike_segment(lap, index))
                continue

            cleaned.append(
                {
                    "segment_index": index,
                    "segment_type": "lap",
                    "label": f"lap {index}",
                    "distance_m": _coerce_float(lap.get("distance"), digits=1),
                    "duration_seconds": _coerce_float(lap.get("duration"), digits=1),
                    "duration_hms": _format_duration(lap.get("duration")),
                    "average_hr": lap.get("averageHR"),
                    "max_hr": lap.get("maxHR"),
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
        splits = _read_json_if_exists(
            self.raw_store,
            self._relative_activity_path(activity_id, "splits.json"),
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
            "segment_breakdown": self._segment_breakdown(splits, discipline=discipline),
            "data_quality": {
                "detail_points": detail_points,
                "has_details": detail_points > 0,
                "has_split_summaries": bool(
                    isinstance(split_summaries, dict)
                    and split_summaries.get("splitSummaries")
                ),
                "has_segment_breakdown": bool(
                    isinstance(splits, dict)
                    and isinstance(splits.get("lapDTOs"), list)
                    and splits.get("lapDTOs")
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
        activity_ids: list[str] | None = None,
        limit: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        selected_ids = (
            [str(item) for item in activity_ids]
            if activity_ids is not None
            else [activity_id] if activity_id is not None else self.available_activity_ids()
        )
        selected_ids = self._filter_activity_ids_by_date(
            selected_ids,
            start_date=start_date,
            end_date=end_date,
        )
        if limit is not None and limit >= 0:
            selected_ids = selected_ids[:limit]

        saved: list[dict[str, Any]] = []
        for current_activity_id in selected_ids:
            saved.append(self.build_and_save_activity_summary(current_activity_id))

        return {
            "activity_count": len(saved),
            "start_date": start_date,
            "end_date": end_date,
            "items": saved,
        }
