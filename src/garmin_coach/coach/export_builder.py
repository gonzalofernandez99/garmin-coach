"""Garmin export builders with multiple detail levels."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..storage.raw_store import RawJsonStore


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _read_json_if_exists(store: RawJsonStore, relative_path: str | Path) -> Any | None:
    try:
        return store.read_json(relative_path)
    except FileNotFoundError:
        return None


class GarminExportBuilder:
    """Build low/medium/full JSON exports using Garmin-derived data only."""

    def __init__(self, settings: Settings) -> None:
        self.raw_store = RawJsonStore(settings.raw_dir)
        self.summary_store = RawJsonStore(settings.summaries_dir)

    def _last_sessions(
        self,
        recent_training: dict[str, Any],
        *,
        limit: int,
        compact: bool,
    ) -> list[dict[str, Any]]:
        sessions = recent_training.get("last_sessions") or []
        sliced = deepcopy(sessions[:limit])
        if not compact:
            return sliced
        compact_sessions: list[dict[str, Any]] = []
        for session in sliced:
            compact_sessions.append(
                {
                    "calendar_date": session.get("calendar_date"),
                    "start_time": session.get("start_time"),
                    "name": session.get("name"),
                    "discipline": session.get("discipline"),
                    "duration_minutes": session.get("duration_minutes"),
                    "distance_km": session.get("distance_km"),
                    "training_load": session.get("training_load"),
                    "average_hr": session.get("average_hr"),
                    "training_effect_label": session.get("training_effect_label"),
                }
            )
        return compact_sessions

    def _compact_window(self, window: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(window, dict):
            return None
        return {
            "session_count": window.get("session_count"),
            "duration_hours": window.get("duration_hours"),
            "distance_km": window.get("distance_km"),
            "training_load": window.get("training_load"),
            "by_discipline": deepcopy(window.get("by_discipline", {})),
        }

    def _rolling_windows(
        self,
        recent_training: dict[str, Any],
        *,
        compact: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in recent_training.items():
            if not key.startswith("rolling_"):
                continue
            payload[key] = self._compact_window(value) if compact else deepcopy(value)
        return payload

    def _compact_daily_context(self, daily_context: dict[str, Any]) -> dict[str, Any]:
        user_summary = daily_context.get("user_summary") or {}
        sleep = daily_context.get("sleep") or {}
        hrv = daily_context.get("hrv") or {}
        readiness = daily_context.get("training_readiness") or {}
        status = daily_context.get("training_status") or {}
        hydration = daily_context.get("hydration") or {}
        race_predictions = daily_context.get("race_predictions") or {}

        return {
            "user_summary": {
                "steps": user_summary.get("steps"),
                "distance_km": user_summary.get("distance_km"),
                "active_kilocalories": user_summary.get("active_kilocalories"),
                "resting_heart_rate": user_summary.get("resting_heart_rate"),
                "body_battery_at_wake": user_summary.get("body_battery_at_wake"),
                "average_stress_level": user_summary.get("average_stress_level"),
                "sleep_hours": user_summary.get("sleep_hours"),
            },
            "sleep": {
                "sleep_score": sleep.get("sleep_score"),
                "sleep_hours": sleep.get("sleep_hours"),
                "deep_sleep_hours": sleep.get("deep_sleep_hours"),
                "rem_sleep_hours": sleep.get("rem_sleep_hours"),
                "avg_sleep_stress": sleep.get("avg_sleep_stress"),
                "feedback": sleep.get("feedback"),
            },
            "hrv": {
                "status": hrv.get("status"),
                "last_night_avg": hrv.get("last_night_avg"),
                "weekly_avg": hrv.get("weekly_avg"),
                "balanced_low": hrv.get("balanced_low"),
                "balanced_upper": hrv.get("balanced_upper"),
            },
            "training_readiness": {
                "score": readiness.get("score"),
                "level": readiness.get("level"),
                "sleep_factor": readiness.get("sleep_factor"),
                "hrv_factor": readiness.get("hrv_factor"),
                "stress_factor": readiness.get("stress_factor"),
                "recovery_time_factor": readiness.get("recovery_time_factor"),
            },
            "training_status": {
                "sport": status.get("sport"),
                "training_status_feedback": status.get("training_status_feedback"),
                "fitness_trend": status.get("fitness_trend"),
                "acwr_status": status.get("acwr_status"),
                "acwr_percent": status.get("acwr_percent"),
                "daily_acute_load": status.get("daily_acute_load"),
                "daily_chronic_load": status.get("daily_chronic_load"),
                "training_balance_feedback": status.get("training_balance_feedback"),
                "vo2max_running": status.get("vo2max_running"),
            },
            "hydration": {
                "current_ml": hydration.get("current_ml"),
                "goal_ml": hydration.get("goal_ml"),
                "sweat_loss_ml": hydration.get("sweat_loss_ml"),
            },
            "race_predictions": {
                "time_5k": race_predictions.get("time_5k"),
                "time_10k": race_predictions.get("time_10k"),
                "time_half_marathon": race_predictions.get("time_half_marathon"),
                "time_marathon": race_predictions.get("time_marathon"),
            },
        }

    def _raw_export_bundle(self, calendar_date: str) -> dict[str, Any]:
        return {
            "user_summary": _read_json_if_exists(
                self.raw_store,
                Path("daily/user_summary") / f"{calendar_date}.json",
            ),
            "sleep": _read_json_if_exists(
                self.raw_store,
                Path("daily/sleep") / f"{calendar_date}.json",
            ),
            "hrv": _read_json_if_exists(
                self.raw_store,
                Path("daily/hrv") / f"{calendar_date}.json",
            ),
            "training_readiness": _read_json_if_exists(
                self.raw_store,
                Path("daily/training_readiness") / f"{calendar_date}.json",
            ),
            "training_status": _read_json_if_exists(
                self.raw_store,
                Path("daily/training_status") / f"{calendar_date}.json",
            ),
            "hydration": _read_json_if_exists(
                self.raw_store,
                Path("daily/hydration") / f"{calendar_date}.json",
            ),
            "body_composition": _read_json_if_exists(
                self.raw_store,
                Path("daily/body_composition") / f"{calendar_date}.json",
            ),
            "activities": _read_json_if_exists(
                self.raw_store,
                Path("daily/activities") / f"{calendar_date}.json",
            ),
            "race_predictions_latest": _read_json_if_exists(
                self.raw_store,
                "training/race_predictions/latest.json",
            ),
        }

    def _has_any_date_specific_raw_data(self, calendar_date: str) -> bool:
        raw_bundle = self._raw_export_bundle(calendar_date)
        for key, value in raw_bundle.items():
            if key == "race_predictions_latest":
                continue
            if value is not None:
                return True
        return False

    def _window_metadata(
        self,
        window_packets: list[dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        if not window_packets:
            return None
        sorted_packets = sorted(
            window_packets,
            key=lambda item: item.get("calendar_date") or "",
        )
        dates = [
            item.get("calendar_date")
            for item in sorted_packets
            if item.get("calendar_date")
        ]
        days_with_any_data = sum(
            1
            for packet in sorted_packets
            if isinstance(packet.get("calendar_date"), str)
            and self._has_any_date_specific_raw_data(packet["calendar_date"])
        )
        return {
            "start_date": dates[0] if dates else None,
            "end_date": dates[-1] if dates else None,
            "days_requested": len(sorted_packets),
            "days_with_any_data": days_with_any_data,
        }

    def _window_daily_summaries(
        self,
        window_packets: list[dict[str, Any]] | None,
        *,
        compact: bool,
    ) -> list[dict[str, Any]]:
        if not window_packets:
            return []
        payloads: list[dict[str, Any]] = []
        for packet in sorted(window_packets, key=lambda item: item.get("calendar_date") or ""):
            daily_context = packet.get("daily_context", {})
            payload: dict[str, Any] = {
                "calendar_date": packet.get("calendar_date"),
                "missing_data": deepcopy(packet.get("missing_data", [])),
            }
            if compact:
                payload["summary"] = self._compact_daily_context(daily_context)
            else:
                payload["daily_context"] = deepcopy(daily_context)
            payloads.append(payload)
        return payloads

    def _window_raw_data(
        self,
        window_packets: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if not window_packets:
            return {}
        by_date: dict[str, Any] = {}
        for packet in sorted(window_packets, key=lambda item: item.get("calendar_date") or ""):
            calendar_date = packet.get("calendar_date")
            if not isinstance(calendar_date, str):
                continue
            by_date[calendar_date] = self._raw_export_bundle(calendar_date)
        return by_date

    def _build_low(
        self,
        *,
        coach_packet: dict[str, Any],
        window_packets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        daily_context = coach_packet.get("daily_context", {})
        recent_training = coach_packet.get("recent_training", {})
        payload = {
            "generated_at": _utc_now(),
            "export_level": "low",
            "calendar_date": coach_packet.get("calendar_date"),
            "summary": self._compact_daily_context(daily_context),
            "recent_training": {
                **self._rolling_windows(recent_training, compact=True),
                "last_sessions": self._last_sessions(
                    recent_training,
                    limit=3,
                    compact=True,
                ),
            },
            "missing_data": deepcopy(coach_packet.get("missing_data", [])),
            "data_quality_flags": deepcopy(coach_packet.get("data_quality_flags", [])),
        }
        window_metadata = self._window_metadata(window_packets)
        if window_metadata is not None:
            payload["window"] = window_metadata
            payload["daily_summaries"] = self._window_daily_summaries(
                window_packets,
                compact=True,
            )
        return payload

    def _build_medium(
        self,
        *,
        coach_packet: dict[str, Any],
        window_packets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        recent_training = coach_packet.get("recent_training", {})
        payload = {
            "generated_at": _utc_now(),
            "export_level": "medium",
            "calendar_date": coach_packet.get("calendar_date"),
            "daily_context": deepcopy(coach_packet.get("daily_context", {})),
            "recent_training": {
                **self._rolling_windows(recent_training, compact=False),
                "last_sessions": self._last_sessions(
                    recent_training,
                    limit=8,
                    compact=False,
                ),
            },
            "missing_data": deepcopy(coach_packet.get("missing_data", [])),
            "data_quality_flags": deepcopy(coach_packet.get("data_quality_flags", [])),
        }
        window_metadata = self._window_metadata(window_packets)
        if window_metadata is not None:
            payload["window"] = window_metadata
            payload["daily_context_by_date"] = self._window_daily_summaries(
                window_packets,
                compact=False,
            )
        return payload

    def _build_full(
        self,
        *,
        coach_packet: dict[str, Any],
        window_packets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        calendar_date = coach_packet["calendar_date"]
        payload = {
            "generated_at": _utc_now(),
            "export_level": "full",
            "calendar_date": calendar_date,
            "summary": {
                "daily_context": deepcopy(coach_packet.get("daily_context", {})),
                "recent_training": deepcopy(coach_packet.get("recent_training", {})),
                "missing_data": deepcopy(coach_packet.get("missing_data", [])),
                "data_quality_flags": deepcopy(
                    coach_packet.get("data_quality_flags", [])
                ),
            },
            "raw_data": self._raw_export_bundle(calendar_date),
        }
        window_metadata = self._window_metadata(window_packets)
        if window_metadata is not None:
            payload["window"] = window_metadata
            payload["summary_by_date"] = self._window_daily_summaries(
                window_packets,
                compact=False,
            )
            payload["raw_data_by_date"] = self._window_raw_data(window_packets)
        return payload

    def build_export(
        self,
        *,
        level: str,
        coach_packet: dict[str, Any],
        window_packets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build one generic export payload."""

        if level == "low":
            return self._build_low(
                coach_packet=coach_packet,
                window_packets=window_packets,
            )
        if level == "medium":
            return self._build_medium(
                coach_packet=coach_packet,
                window_packets=window_packets,
            )
        if level == "full":
            return self._build_full(
                coach_packet=coach_packet,
                window_packets=window_packets,
            )
        raise ValueError(f"Unsupported export level '{level}'.")

    def build_and_save_export(
        self,
        *,
        level: str,
        coach_packet: dict[str, Any],
        window_packets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build and persist one generic export payload."""

        payload = self.build_export(
            level=level,
            coach_packet=coach_packet,
            window_packets=window_packets,
        )
        calendar_date = coach_packet["calendar_date"]
        dated_result = self.summary_store.save_json(
            Path("coach/exports") / level / f"{calendar_date}.json",
            payload,
        )
        latest_result = self.summary_store.save_json(
            Path("coach/exports") / level / "latest.json",
            payload,
        )
        return {
            "level": level,
            "calendar_date": calendar_date,
            "dated_path": str(dated_result.path),
            "latest_path": str(latest_result.path),
            "changed": bool(dated_result.changed or latest_result.changed),
        }
