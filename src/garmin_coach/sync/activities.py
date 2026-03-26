"""Recent activity sync service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
from typing import Any, Callable

from ..garmin_client import GarminCoachClient
from ..storage.raw_store import RawJsonStore
from ..utils.activities import activity_list_from_payload, dedupe_activities, extract_activity_id
from ..utils.dates import inclusive_date_range, parse_iso_date
from .daily import DailySyncService

logger = logging.getLogger(__name__)


class ActivitySyncService:
    """Synchronize a recent activity window and fetch per-activity details."""

    def __init__(
        self,
        client: GarminCoachClient,
        store: RawJsonStore,
        daily_sync: DailySyncService,
    ) -> None:
        self.client = client
        self.store = store
        self.daily_sync = daily_sync

    def _sync_activity_resource(
        self,
        *,
        activity_id: str,
        resource: str,
        relative_path: Path,
        fetcher: Callable[[], Any],
    ) -> dict[str, Any]:
        try:
            payload = fetcher()
            result = self.store.save_json(relative_path, payload)
            return {
                "resource": resource,
                "status": "updated" if result.changed else "unchanged",
                "path": str(result.path),
                "sha256": result.sha256,
            }
        except self.client.dependencies.auth_error:
            raise
        except Exception as exc:
            logger.warning(
                "Skipping activity resource %s for activity %s: %s",
                resource,
                activity_id,
                exc,
            )
            return {
                "resource": resource,
                "status": "error",
                "message": str(exc),
            }

    def _save_report(
        self,
        *,
        command: str,
        started_at: str,
        finished_at: str,
        report: dict[str, Any],
        status: str,
    ) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        save_result = self.store.save_json(
            Path("sync_reports") / command / f"{stamp}.json",
            report,
        )
        sqlite_index = self.store.sqlite_index
        if sqlite_index is not None:
            sqlite_index.log_sync_run(
                command=command,
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                details=report,
            )
        return str(save_result.path)

    def sync_window(self, end_date: str, *, days: int = 30) -> dict[str, Any]:
        """Sync the daily raw window and activity details."""

        started_at = datetime.now(UTC).isoformat()
        end = parse_iso_date(end_date)
        start = end - timedelta(days=days - 1)

        daily_reports: list[dict[str, Any]] = []
        collected_activities: list[dict[str, Any]] = []

        for index, current in enumerate(inclusive_date_range(start, end)):
            cdate = current.isoformat()
            daily_report = self.daily_sync.sync_date(
                cdate,
                include_account_snapshots=index == 0,
            )
            daily_reports.append(
                {
                    "date": cdate,
                    "status": daily_report["status"],
                    "error_count": daily_report["error_count"],
                    "report_path": daily_report["report_path"],
                }
            )

            activities_path = Path("daily/activities") / f"{cdate}.json"
            try:
                payload = self.store.read_json(activities_path)
                collected_activities.extend(activity_list_from_payload(payload))
            except FileNotFoundError:
                logger.debug("No daily activities artifact found for %s", cdate)

        activities = dedupe_activities(collected_activities)
        index_result = self.store.save_json(
            Path("activities/index") / f"{end_date}_last_{days}_days.json",
            activities,
        )

        activity_reports: list[dict[str, Any]] = []
        for activity in activities:
            activity_id = extract_activity_id(activity)
            if activity_id is None:
                continue

            activity_root = Path("activities/by_id") / activity_id
            list_entry = self.store.save_json(activity_root / "list_entry.json", activity)

            resources = [
                self._sync_activity_resource(
                    activity_id=activity_id,
                    resource="summary",
                    relative_path=activity_root / "summary.json",
                    fetcher=lambda activity_id=activity_id: self.client.fetch_activity_summary(
                        activity_id
                    ),
                ),
                self._sync_activity_resource(
                    activity_id=activity_id,
                    resource="details",
                    relative_path=activity_root / "details.json",
                    fetcher=lambda activity_id=activity_id: self.client.fetch_activity_details(
                        activity_id
                    ),
                ),
                self._sync_activity_resource(
                    activity_id=activity_id,
                    resource="splits",
                    relative_path=activity_root / "splits.json",
                    fetcher=lambda activity_id=activity_id: self.client.fetch_activity_splits(
                        activity_id
                    ),
                ),
                self._sync_activity_resource(
                    activity_id=activity_id,
                    resource="typed_splits",
                    relative_path=activity_root / "typed_splits.json",
                    fetcher=lambda activity_id=activity_id: self.client.fetch_activity_typed_splits(
                        activity_id
                    ),
                ),
                self._sync_activity_resource(
                    activity_id=activity_id,
                    resource="split_summaries",
                    relative_path=activity_root / "split_summaries.json",
                    fetcher=lambda activity_id=activity_id: self.client.fetch_activity_split_summaries(
                        activity_id
                    ),
                ),
            ]

            activity_reports.append(
                {
                    "activity_id": activity_id,
                    "list_entry_status": "updated" if list_entry.changed else "unchanged",
                    "list_entry_path": str(list_entry.path),
                    "resources": resources,
                }
            )

        errors = [
            report
            for report in activity_reports
            for item in report["resources"]
            if item["status"] == "error"
        ]
        daily_errors = sum(report["error_count"] for report in daily_reports)
        status = "partial" if errors or daily_errors else "success"
        finished_at = datetime.now(UTC).isoformat()
        report: dict[str, Any] = {
            "command": "sync-last-30-days",
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": days,
            "daily_reports": daily_reports,
            "activity_count": len(activities),
            "activity_index_path": str(index_result.path),
            "activity_index_status": "updated" if index_result.changed else "unchanged",
            "activities": activity_reports,
            "daily_error_count": daily_errors,
            "activity_error_count": len(errors),
        }
        report["report_path"] = self._save_report(
            command="sync-last-30-days",
            started_at=started_at,
            finished_at=finished_at,
            report=report,
            status=status,
        )
        return report
