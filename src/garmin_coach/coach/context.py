"""Build Garmin-derived coaching context artifacts."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import Settings
from ..storage.raw_store import RawJsonStore
from ..utils.activities import activity_list_from_payload, extract_activity_start
from ..utils.dates import parse_iso_date


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json_if_exists(store: RawJsonStore, relative_path: str | Path) -> Any | None:
    try:
        return store.read_json(relative_path)
    except FileNotFoundError:
        return None


def _parse_birth_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _age_from_birth_date(value: str | None, *, reference_date: date | None = None) -> int | None:
    birth_date = _parse_birth_date(value)
    if birth_date is None:
        return None
    current = reference_date or datetime.now(UTC).date()
    years = current.year - birth_date.year
    if (current.month, current.day) < (birth_date.month, birth_date.day):
        years -= 1
    return max(years, 0)


def _age_bracket(age: int | None) -> str | None:
    if age is None:
        return None
    lower = (age // 5) * 5
    return f"{lower}-{lower + 4}"


def _coerce_weight_kg(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    if numeric > 250:
        numeric /= 1000.0
    return round(numeric, 1)


def _coerce_height_cm(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    if numeric < 3:
        numeric *= 100.0
    return round(numeric, 1)


def _sanitize_heart_rate(value: Any) -> int | None:
    if value is None:
        return None
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    if 60 <= numeric <= 230:
        return numeric
    return None


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


def _activity_type_key(activity: dict[str, Any]) -> str:
    activity_type = activity.get("activityType")
    if isinstance(activity_type, dict):
        type_key = activity_type.get("typeKey")
        if isinstance(type_key, str):
            return type_key
    summary = activity.get("summaryDTO")
    if isinstance(summary, dict):
        activity_type = summary.get("activityTypeDTO")
        if isinstance(activity_type, dict):
            type_key = activity_type.get("typeKey")
            if isinstance(type_key, str):
                return type_key
    return "unknown"


def _activity_discipline(type_key: str) -> str:
    lowered = type_key.lower()
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


def _coerce_float(value: Any, *, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _extract_latest_weight(raw: Any) -> float | None:
    if not isinstance(raw, dict):
        return None
    entries = raw.get("dateWeightList")
    if isinstance(entries, list):
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            for key in ("weightKG", "weight", "weightInKg"):
                value = _coerce_weight_kg(entry.get(key))
                if value is not None:
                    return value
    total_average = raw.get("totalAverage")
    if isinstance(total_average, dict):
        return _coerce_weight_kg(total_average.get("weight"))
    return None


def _zone_times_minutes(activity: dict[str, Any], prefix: str) -> dict[str, float] | None:
    payload: dict[str, float] = {}
    for zone in range(1, 6):
        value = _coerce_float(
            None
            if activity.get(f"{prefix}_{zone}") is None
            else float(activity.get(f"{prefix}_{zone}")) / 60.0,
            digits=2,
        )
        if value is not None:
            payload[f"z{zone}"] = value
    return payload or None


class CoachContextBuilder:
    """Read Garmin raw artifacts and derive normalized coaching context."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.raw_store = RawJsonStore(settings.raw_dir)
        self.normalized_store = RawJsonStore(settings.normalized_dir)
        self.summary_store = RawJsonStore(settings.summaries_dir)

    def _daily_resource_dir(self, resource: str) -> Path:
        return self.settings.raw_dir / "daily" / resource

    def available_daily_dates(self, resource: str) -> list[str]:
        directory = self._daily_resource_dir(resource)
        if not directory.exists():
            return []
        dates: list[str] = []
        for path in directory.glob("*.json"):
            try:
                parse_iso_date(path.stem)
            except ValueError:
                continue
            dates.append(path.stem)
        return sorted(dates)

    def latest_daily_date(self) -> str | None:
        candidates: set[str] = set()
        for resource in ("user_summary", "training_readiness", "training_status", "activities"):
            candidates.update(self.available_daily_dates(resource))
        return max(candidates) if candidates else None

    def _load_daily(self, resource: str, cdate: str) -> Any | None:
        return _read_json_if_exists(
            self.raw_store,
            Path("daily") / resource / f"{cdate}.json",
        )

    def _load_latest_daily(self, resource: str) -> tuple[str | None, Any | None]:
        dates = self.available_daily_dates(resource)
        if not dates:
            return None, None
        latest = dates[-1]
        return latest, self._load_daily(resource, latest)

    def _load_account(self, relative_path: str) -> Any | None:
        return _read_json_if_exists(self.raw_store, relative_path)

    def build_athlete_profile(self) -> dict[str, Any]:
        """Return a Garmin-derived athlete profile with PII minimized."""

        user_settings_raw = self._load_account("account/user_settings/current.json")
        profile_settings = self._load_account("account/profile_settings/current.json")
        primary_device_raw = self._load_account(
            "device/primary_training_device/current.json"
        )
        latest_training_status_date, training_status_raw = self._load_latest_daily(
            "training_status"
        )
        latest_body_composition_date, body_comp_raw = self._load_latest_daily(
            "body_composition"
        )

        user_data = (
            user_settings_raw.get("userData", {})
            if isinstance(user_settings_raw, dict)
            else {}
        )
        age = _age_from_birth_date(user_data.get("birthDate"))
        lactate_threshold_heart_rate = _sanitize_heart_rate(
            user_data.get("lactateThresholdHeartRate")
        )
        weight_kg = _coerce_weight_kg(user_data.get("weight"))
        if weight_kg is None:
            weight_kg = _extract_latest_weight(body_comp_raw)

        device_summary: dict[str, Any] = {}
        if isinstance(primary_device_raw, dict):
            device_weights = (
                primary_device_raw.get("PrimaryTrainingDevices", {})
                .get("deviceWeights", [])
            )
            if isinstance(device_weights, list) and device_weights:
                first = device_weights[0]
                if isinstance(first, dict):
                    device_summary["primary_training_device"] = first.get("displayName")

            registered_devices = primary_device_raw.get("RegisteredDevices")
            if isinstance(registered_devices, list):
                for device in registered_devices:
                    if not isinstance(device, dict) or not device.get("primary"):
                        continue
                    device_summary.update(
                        {
                            "device_type": device.get("deviceTypeSimpleName"),
                            "firmware_version": device.get("currentFirmwareVersion"),
                            "hrv_status_capable": bool(device.get("hrvStatusCapable")),
                            "race_predictions_capable": bool(
                                device.get("racePredictionsRunCapable")
                            ),
                            "primary_training_capable": bool(
                                device.get("primaryTrainingCapable")
                            ),
                        }
                    )
                    break

        training_status_summary = {}
        if isinstance(training_status_raw, dict):
            most_recent_vo2max = training_status_raw.get("mostRecentVO2Max", {})
            if isinstance(most_recent_vo2max, dict):
                generic_vo2max = most_recent_vo2max.get("generic", {})
                if isinstance(generic_vo2max, dict):
                    training_status_summary["vo2max_running"] = generic_vo2max.get(
                        "vo2MaxValue"
                    )
                training_status_summary["vo2max_cycling"] = most_recent_vo2max.get(
                    "cycling"
                )

        athlete = {
            "age": age,
            "age_bracket": _age_bracket(age),
            "gender": user_data.get("gender"),
            "height_cm": _coerce_height_cm(user_data.get("height")),
            "weight_kg": weight_kg,
            "timezone": (
                profile_settings.get("timeZone")
                if isinstance(profile_settings, dict)
                else None
            ),
            "preferred_locale": (
                profile_settings.get("preferredLocale")
                if isinstance(profile_settings, dict)
                else None
            ),
            "measurement_system": (
                profile_settings.get("measurementSystem")
                if isinstance(profile_settings, dict)
                else None
            ),
            "vo2max_running": training_status_summary.get("vo2max_running")
            or user_data.get("vo2MaxRunning"),
            "vo2max_cycling": user_data.get("vo2MaxCycling"),
            "lactate_threshold_heart_rate": lactate_threshold_heart_rate,
            "ftp_auto_detected": user_data.get("ftpAutoDetected"),
            "threshold_heart_rate_auto_detected": user_data.get(
                "thresholdHeartRateAutoDetected"
            ),
        }

        data_quality_flags: list[str] = []
        if user_data.get("lactateThresholdHeartRate") and lactate_threshold_heart_rate is None:
            data_quality_flags.append(
                "La frecuencia cardiaca de umbral guardada en Garmin parece inconsistente y se omite del contexto."
            )
        if athlete["weight_kg"] is None:
            data_quality_flags.append(
                "No hay un peso reciente confiable disponible en Garmin."
            )

        profile = {
            "generated_at": _utc_now(),
            "source_dates": {
                "training_status": latest_training_status_date,
                "body_composition": latest_body_composition_date,
            },
            "athlete": athlete,
            "device": device_summary,
            "known_metrics": {
                "daily_metrics_available": sorted(
                    resource
                    for resource in (
                        "user_summary",
                        "sleep",
                        "stress",
                        "body_battery",
                        "resting_hr",
                        "hrv",
                        "spo2",
                        "body_composition",
                        "hydration",
                        "nutrition_food_log",
                        "training_readiness",
                        "training_status",
                        "activities",
                    )
                    if self.available_daily_dates(resource)
                )
            },
            "data_quality_flags": data_quality_flags,
            "privacy": {
                "pii_filtered": True,
                "excluded_fields": [
                    "fullName",
                    "displayName",
                    "profile images",
                    "userId",
                    "coordinates",
                    "social metadata",
                ],
            },
        }
        return profile

    def build_and_save_athlete_profile(self) -> dict[str, Any]:
        """Build and persist the current athlete profile."""

        profile = self.build_athlete_profile()
        self.normalized_store.save_json("coach/athlete_profile/current.json", profile)
        return profile

    def _summarize_user_summary(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        return {
            "calendar_date": raw.get("calendarDate"),
            "steps": raw.get("totalSteps"),
            "distance_km": _coerce_float(
                None
                if raw.get("totalDistanceMeters") is None
                else raw.get("totalDistanceMeters") / 1000.0
            ),
            "active_kilocalories": raw.get("activeKilocalories"),
            "resting_heart_rate": raw.get("restingHeartRate"),
            "body_battery_at_wake": raw.get("bodyBatteryAtWakeTime"),
            "average_stress_level": raw.get("averageStressLevel"),
            "sleep_hours": _coerce_float(
                None
                if raw.get("sleepingSeconds") is None
                else raw.get("sleepingSeconds") / 3600.0
            ),
            "latest_spo2": raw.get("latestSpo2"),
            "avg_waking_respiration": raw.get("avgWakingRespirationValue"),
        }

    def _summarize_sleep(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        sleep = raw.get("dailySleepDTO", {})
        if not isinstance(sleep, dict):
            return None
        scores = sleep.get("sleepScores", {})
        overall = scores.get("overall", {}) if isinstance(scores, dict) else {}
        return {
            "calendar_date": sleep.get("calendarDate"),
            "sleep_score": overall.get("value"),
            "sleep_score_qualifier": overall.get("qualifierKey"),
            "sleep_hours": _coerce_float(
                None if sleep.get("sleepTimeSeconds") is None else sleep.get("sleepTimeSeconds") / 3600.0
            ),
            "deep_sleep_hours": _coerce_float(
                None if sleep.get("deepSleepSeconds") is None else sleep.get("deepSleepSeconds") / 3600.0
            ),
            "light_sleep_hours": _coerce_float(
                None if sleep.get("lightSleepSeconds") is None else sleep.get("lightSleepSeconds") / 3600.0
            ),
            "rem_sleep_hours": _coerce_float(
                None if sleep.get("remSleepSeconds") is None else sleep.get("remSleepSeconds") / 3600.0
            ),
            "awake_minutes": _coerce_float(
                None if sleep.get("awakeSleepSeconds") is None else sleep.get("awakeSleepSeconds") / 60.0
            ),
            "average_respiration_value": sleep.get("averageRespirationValue"),
            "avg_sleep_stress": sleep.get("avgSleepStress"),
            "insight": sleep.get("sleepScoreInsight"),
            "feedback": sleep.get("sleepScoreFeedback"),
        }

    def _summarize_hrv(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        summary = raw.get("hrvSummary")
        if not isinstance(summary, dict):
            return None
        baseline = summary.get("baseline", {})
        if not isinstance(baseline, dict):
            baseline = {}
        return {
            "calendar_date": summary.get("calendarDate"),
            "status": summary.get("status"),
            "feedback_phrase": summary.get("feedbackPhrase"),
            "last_night_avg": summary.get("lastNightAvg"),
            "weekly_avg": summary.get("weeklyAvg"),
            "balanced_low": baseline.get("balancedLow"),
            "balanced_upper": baseline.get("balancedUpper"),
        }

    def _summarize_training_readiness(self, raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if not isinstance(raw, dict):
            return None
        return {
            "calendar_date": raw.get("calendarDate"),
            "score": raw.get("score"),
            "level": raw.get("level"),
            "sleep_score": raw.get("sleepScore"),
            "hrv_weekly_average": raw.get("hrvWeeklyAverage"),
            "recovery_time_seconds": raw.get("recoveryTime"),
            "feedback_short": raw.get("feedbackShort"),
            "feedback_long": raw.get("feedbackLong"),
            "sleep_factor": raw.get("sleepScoreFactorFeedback"),
            "hrv_factor": raw.get("hrvFactorFeedback"),
            "stress_factor": raw.get("stressHistoryFactorFeedback"),
            "recovery_time_factor": raw.get("recoveryTimeFactorFeedback"),
        }

    def _summarize_training_status(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None

        latest_training_status = raw.get("mostRecentTrainingStatus", {})
        latest_training_data: dict[str, Any] = {}
        if isinstance(latest_training_status, dict):
            training_data = latest_training_status.get("latestTrainingStatusData", {})
            if isinstance(training_data, dict) and training_data:
                latest_training_data = next(
                    (value for value in training_data.values() if isinstance(value, dict)),
                    {},
                )

        acute_load = latest_training_data.get("acuteTrainingLoadDTO", {})
        if not isinstance(acute_load, dict):
            acute_load = {}

        load_balance = raw.get("mostRecentTrainingLoadBalance", {})
        latest_balance: dict[str, Any] = {}
        if isinstance(load_balance, dict):
            balance_map = load_balance.get("metricsTrainingLoadBalanceDTOMap", {})
            if isinstance(balance_map, dict) and balance_map:
                latest_balance = next(
                    (value for value in balance_map.values() if isinstance(value, dict)),
                    {},
                )

        most_recent_vo2max = raw.get("mostRecentVO2Max", {})
        generic_vo2max = (
            most_recent_vo2max.get("generic", {})
            if isinstance(most_recent_vo2max, dict)
            else {}
        )
        if not isinstance(generic_vo2max, dict):
            generic_vo2max = {}

        return {
            "calendar_date": latest_training_data.get("calendarDate"),
            "sport": latest_training_data.get("sport"),
            "training_status_feedback": latest_training_data.get(
                "trainingStatusFeedbackPhrase"
            ),
            "fitness_trend": latest_training_data.get("fitnessTrend"),
            "acwr_status": acute_load.get("acwrStatus"),
            "acwr_percent": acute_load.get("acwrPercent"),
            "daily_acute_load": acute_load.get("dailyTrainingLoadAcute"),
            "daily_chronic_load": acute_load.get("dailyTrainingLoadChronic"),
            "training_balance_feedback": latest_balance.get(
                "trainingBalanceFeedbackPhrase"
            ),
            "monthly_aerobic_low": latest_balance.get("monthlyLoadAerobicLow"),
            "monthly_aerobic_high": latest_balance.get("monthlyLoadAerobicHigh"),
            "monthly_anaerobic": latest_balance.get("monthlyLoadAnaerobic"),
            "vo2max_running": generic_vo2max.get("vo2MaxValue"),
        }

    def _summarize_hydration(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        return {
            "calendar_date": raw.get("calendarDate"),
            "current_ml": raw.get("valueInML"),
            "goal_ml": raw.get("goalInML"),
            "sweat_loss_ml": raw.get("sweatLossInML"),
            "activity_intake_ml": raw.get("activityIntakeInML"),
        }

    def _summarize_body_composition(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        return {
            "latest_weight_kg": _extract_latest_weight(raw),
        }

    def _summarize_race_predictions(self, raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        return {
            "calendar_date": raw.get("calendarDate"),
            "time_5k": _format_duration(raw.get("time5K")),
            "time_10k": _format_duration(raw.get("time10K")),
            "time_half_marathon": _format_duration(raw.get("timeHalfMarathon")),
            "time_marathon": _format_duration(raw.get("timeMarathon")),
        }

    def _activity_summary(self, activity: dict[str, Any], *, fallback_date: str) -> dict[str, Any]:
        start = extract_activity_start(activity)
        type_key = _activity_type_key(activity)
        discipline = _activity_discipline(type_key)
        distance_meters = activity.get("distance")
        average_speed = activity.get("averageSpeed")
        pace_min_per_km = None
        if discipline == "run" and average_speed:
            try:
                meters_per_second = float(average_speed)
                if meters_per_second > 0:
                    pace_min_per_km = round(1000.0 / meters_per_second / 60.0, 2)
            except (TypeError, ValueError):
                pace_min_per_km = None

        sport_specific: dict[str, Any] = {
            "steps": activity.get("steps"),
            "cadence_spm": activity.get("averageRunningCadenceInStepsPerMinute")
            or activity.get("averageSwimCadenceInStrokesPerMinute"),
            "stride_length_cm": _coerce_float(activity.get("avgStrideLength"), digits=1),
            "avg_power": activity.get("avgPower"),
            "normalized_power": activity.get("normPower"),
            "avg_grade_adjusted_speed_kmh": _coerce_float(
                None
                if activity.get("avgGradeAdjustedSpeed") is None
                else float(activity.get("avgGradeAdjustedSpeed")) * 3.6,
                digits=2,
            ),
            "elevation_gain_m": activity.get("elevationGain"),
            "elevation_loss_m": activity.get("elevationLoss"),
            "pool_length_m": _coerce_float(
                None
                if activity.get("poolLength") is None
                else float(activity.get("poolLength")) / 100.0,
                digits=1,
            ),
            "active_lengths": activity.get("activeLengths"),
            "strokes": activity.get("strokes"),
            "swolf": activity.get("averageSwolf"),
            "avg_respiration_rate": _coerce_float(activity.get("avgRespirationRate"), digits=1),
            "water_estimated_ml": activity.get("waterEstimated"),
            "moderate_intensity_minutes": activity.get("moderateIntensityMinutes"),
            "vigorous_intensity_minutes": activity.get("vigorousIntensityMinutes"),
        }

        return {
            "activity_id": str(activity.get("activityId") or activity.get("activityUUID")),
            "calendar_date": fallback_date,
            "start_time": None if start is None else start.isoformat(),
            "name": activity.get("activityName"),
            "discipline": discipline,
            "type_key": type_key,
            "duration_minutes": _coerce_float(
                None if activity.get("duration") is None else activity.get("duration") / 60.0
            ),
            "moving_minutes": _coerce_float(
                None
                if activity.get("movingDuration") is None
                else activity.get("movingDuration") / 60.0
            ),
            "distance_km": _coerce_float(
                None if distance_meters is None else float(distance_meters) / 1000.0
            ),
            "training_load": _coerce_float(activity.get("activityTrainingLoad"), digits=1),
            "average_hr": activity.get("averageHR"),
            "max_hr": activity.get("maxHR"),
            "average_speed_kmh": _coerce_float(
                None if average_speed is None else float(average_speed) * 3.6
            ),
            "pace_min_per_km": pace_min_per_km,
            "aerobic_training_effect": activity.get("aerobicTrainingEffect"),
            "anaerobic_training_effect": activity.get("anaerobicTrainingEffect"),
            "training_effect_label": activity.get("trainingEffectLabel"),
            "heart_rate_zone_times_minutes": _zone_times_minutes(
                activity,
                "hrTimeInZone",
            ),
            "power_zone_times_minutes": _zone_times_minutes(
                activity,
                "powerTimeInZone",
            ),
            "sport_specific": sport_specific,
        }

    def _recent_activity_summaries(
        self,
        cdate: str,
        *,
        window_days: int = 28,
    ) -> dict[str, Any]:
        end_date = parse_iso_date(cdate)
        normalized_window_days = max(int(window_days), 1)
        start_date = end_date - timedelta(days=normalized_window_days - 1)
        activities: list[dict[str, Any]] = []
        seen_activity_keys: set[str] = set()

        for current_date in self.available_daily_dates("activities"):
            current = parse_iso_date(current_date)
            if current < start_date or current > end_date:
                continue
            payload = self._load_daily("activities", current_date)
            if payload is None:
                continue
            for activity in activity_list_from_payload(payload):
                summary = self._activity_summary(activity, fallback_date=current_date)
                activity_key = (
                    summary.get("activity_id")
                    or summary.get("start_time")
                    or f"{summary.get('name')}::{summary['calendar_date']}"
                )
                if activity_key in seen_activity_keys:
                    continue
                seen_activity_keys.add(activity_key)
                activities.append(summary)

        activities.sort(
            key=lambda item: item.get("start_time") or item["calendar_date"],
            reverse=True,
        )

        def aggregate_window(window_days: int) -> dict[str, Any]:
            window_start = end_date - timedelta(days=window_days - 1)
            in_window = [
                activity
                for activity in activities
                if window_start <= parse_iso_date(activity["calendar_date"]) <= end_date
            ]
            by_discipline: dict[str, dict[str, Any]] = defaultdict(
                lambda: {
                    "session_count": 0,
                    "duration_hours": 0.0,
                    "distance_km": 0.0,
                    "training_load": 0.0,
                }
            )
            totals = {
                "session_count": len(in_window),
                "duration_hours": 0.0,
                "distance_km": 0.0,
                "training_load": 0.0,
            }
            for activity in in_window:
                duration_hours = round(
                    float(activity.get("duration_minutes") or 0.0) / 60.0,
                    2,
                )
                distance_km = float(activity.get("distance_km") or 0.0)
                training_load = float(activity.get("training_load") or 0.0)
                totals["duration_hours"] += duration_hours
                totals["distance_km"] += distance_km
                totals["training_load"] += training_load

                bucket = by_discipline[activity["discipline"]]
                bucket["session_count"] += 1
                bucket["duration_hours"] += duration_hours
                bucket["distance_km"] += distance_km
                bucket["training_load"] += training_load

            totals["duration_hours"] = round(totals["duration_hours"], 2)
            totals["distance_km"] = round(totals["distance_km"], 1)
            totals["training_load"] = round(totals["training_load"], 1)

            normalized_disciplines = {
                discipline: {
                    "session_count": bucket["session_count"],
                    "duration_hours": round(bucket["duration_hours"], 2),
                    "distance_km": round(bucket["distance_km"], 1),
                    "training_load": round(bucket["training_load"], 1),
                }
                for discipline, bucket in sorted(by_discipline.items())
            }
            return {
                **totals,
                "by_discipline": normalized_disciplines,
            }

        return {
            "last_sessions": activities[:5],
            "rolling_7d": aggregate_window(min(7, normalized_window_days)),
            f"rolling_{normalized_window_days}d": aggregate_window(
                normalized_window_days
            ),
        }

    def build_coach_packet(
        self,
        cdate: str | None = None,
        *,
        athlete_profile: dict[str, Any] | None = None,
        recent_training_window_days: int = 28,
    ) -> dict[str, Any]:
        """Return a per-day coaching packet built from Garmin raw artifacts."""

        calendar_date = cdate or self.latest_daily_date()
        if calendar_date is None:
            raise FileNotFoundError("No daily Garmin data available to build a coach packet.")

        athlete_profile = athlete_profile or self.build_athlete_profile()
        user_summary = self._summarize_user_summary(
            self._load_daily("user_summary", calendar_date)
        )
        sleep = self._summarize_sleep(self._load_daily("sleep", calendar_date))
        hrv = self._summarize_hrv(self._load_daily("hrv", calendar_date))
        training_readiness = self._summarize_training_readiness(
            self._load_daily("training_readiness", calendar_date)
        )
        training_status = self._summarize_training_status(
            self._load_daily("training_status", calendar_date)
        )
        hydration = self._summarize_hydration(self._load_daily("hydration", calendar_date))
        body_composition = self._summarize_body_composition(
            self._load_daily("body_composition", calendar_date)
        )
        race_predictions = self._summarize_race_predictions(
            self._load_account("training/race_predictions/latest.json")
        )

        missing_data = [
            name
            for name, value in (
                ("user_summary", user_summary),
                ("sleep", sleep),
                ("hrv", hrv),
                ("training_readiness", training_readiness),
                ("training_status", training_status),
            )
            if value is None
        ]

        packet = {
            "generated_at": _utc_now(),
            "calendar_date": calendar_date,
            "athlete_profile_snapshot": athlete_profile.get("athlete", {}),
            "daily_context": {
                "user_summary": user_summary,
                "sleep": sleep,
                "hrv": hrv,
                "training_readiness": training_readiness,
                "training_status": training_status,
                "hydration": hydration,
                "body_composition": body_composition,
                "race_predictions": race_predictions,
            },
            "recent_training": self._recent_activity_summaries(
                calendar_date,
                window_days=recent_training_window_days,
            ),
            "missing_data": missing_data,
            "data_quality_flags": athlete_profile.get("data_quality_flags", []),
        }
        return packet

    def build_and_save_coach_packet(
        self,
        cdate: str | None = None,
        *,
        athlete_profile: dict[str, Any] | None = None,
        recent_training_window_days: int = 28,
    ) -> dict[str, Any]:
        """Build and persist a daily coaching packet."""

        packet = self.build_coach_packet(
            cdate,
            athlete_profile=athlete_profile,
            recent_training_window_days=recent_training_window_days,
        )
        self.summary_store.save_json(
            Path("coach/packets") / f"{packet['calendar_date']}.json",
            packet,
        )
        return packet
