"""Top-level coach orchestration service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..config import Settings
from ..storage.raw_store import RawJsonStore
from ..summary.activity_summary import ActivitySummaryBuilder
from .context import CoachContextBuilder
from .export_builder import GarminExportBuilder


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class CoachService:
    """Orchestrate Garmin-derived context, exports and activity summaries."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.context_builder = CoachContextBuilder(settings)
        self.export_builder = GarminExportBuilder(settings)
        self.activity_summary_builder = ActivitySummaryBuilder(
            RawJsonStore(settings.raw_dir),
            RawJsonStore(settings.summaries_dir),
        )

    def build_context(
        self,
        cdate: str | None = None,
        *,
        recent_training_window_days: int = 28,
    ) -> dict[str, Any]:
        """Build and persist the current athlete profile and coach packet."""

        athlete_profile = self.context_builder.build_and_save_athlete_profile()
        coach_packet = self.context_builder.build_and_save_coach_packet(
            cdate,
            athlete_profile=athlete_profile,
            recent_training_window_days=recent_training_window_days,
        )
        return {
            "athlete_profile": athlete_profile,
            "coach_packet": coach_packet,
        }

    def build_exports(
        self,
        cdate: str | None = None,
        *,
        level: str = "all",
        window_days: int = 1,
    ) -> dict[str, Any]:
        """Build low/medium/full Garmin-only JSON exports."""

        if level not in {"low", "medium", "full", "all"}:
            raise ValueError(
                "Unsupported export level. Use one of: low, medium, full, all."
            )
        if window_days < 1:
            raise ValueError("window_days must be >= 1")

        athlete_profile = self.context_builder.build_and_save_athlete_profile()
        end_date = cdate or self.context_builder.latest_daily_date()
        if end_date is None:
            raise FileNotFoundError("No daily Garmin data available to build exports.")
        recent_training_window_days = 28 if window_days == 1 else window_days
        coach_packet = self.context_builder.build_and_save_coach_packet(
            end_date,
            athlete_profile=athlete_profile,
            recent_training_window_days=recent_training_window_days,
        )
        window_packets = None
        if window_days > 1:
            from ..utils.dates import inclusive_date_range, parse_iso_date

            end = parse_iso_date(end_date)
            start = end - timedelta(days=window_days - 1)
            window_packets = [
                self.context_builder.build_coach_packet(
                    item.isoformat(),
                    athlete_profile=athlete_profile,
                    recent_training_window_days=recent_training_window_days,
                )
                for item in inclusive_date_range(start, end)
            ]
        levels = ("low", "medium", "full") if level == "all" else (level,)

        exports = {
            export_level: self.export_builder.build_and_save_export(
                level=export_level,
                coach_packet=coach_packet,
                window_packets=window_packets,
            )
            for export_level in levels
        }

        return {
            "generated_at": _utc_now(),
            "calendar_date": coach_packet.get("calendar_date"),
            "requested_level": level,
            "window_days": window_days,
            "exports": exports,
        }

    def build_activity_summaries(
        self,
        *,
        activity_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Build and persist cleaned JSON summaries for synced activities."""

        return self.activity_summary_builder.build_and_save_activity_summaries(
            activity_id=activity_id,
            limit=limit,
        )
