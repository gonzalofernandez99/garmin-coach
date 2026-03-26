"""Daily raw sync service."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any, Callable

from ..garmin_client import GarminCoachClient
from ..storage.raw_store import RawJsonStore

logger = logging.getLogger(__name__)


class DailySyncService:
    """Synchronize account snapshots and daily raw Garmin resources."""

    def __init__(self, client: GarminCoachClient, store: RawJsonStore) -> None:
        self.client = client
        self.store = store

    def _artifact_status(self, resource: str, result: Any) -> dict[str, Any]:
        return {
            "resource": resource,
            "status": "updated" if result.changed else "unchanged",
            "path": str(result.path),
            "sha256": result.sha256,
        }

    def _sync_resource(
        self,
        *,
        resource: str,
        relative_path: Path,
        fetcher: Callable[[], Any],
    ) -> dict[str, Any]:
        try:
            payload = fetcher()
            result = self.store.save_json(relative_path, payload)
            return self._artifact_status(resource, result)
        except self.client.dependencies.auth_error:
            raise
        except Exception as exc:
            logger.warning("Skipping Garmin resource %s: %s", resource, exc)
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

    def sync_date(
        self,
        cdate: str,
        *,
        include_account_snapshots: bool = True,
    ) -> dict[str, Any]:
        """Sync one date worth of raw Garmin data."""

        started_at = datetime.now(UTC).isoformat()
        self.client.login()

        account_specs: list[tuple[str, Path, Callable[[], Any]]] = [
            ("profile", Path("account/profile/current.json"), self.client.fetch_profile),
            (
                "profile_settings",
                Path("account/profile_settings/current.json"),
                self.client.fetch_profile_settings,
            ),
            (
                "user_settings",
                Path("account/user_settings/current.json"),
                self.client.fetch_user_settings,
            ),
            ("devices", Path("device/devices/current.json"), self.client.fetch_devices),
            (
                "primary_training_device",
                Path("device/primary_training_device/current.json"),
                self.client.fetch_primary_training_device,
            ),
            (
                "device_last_used",
                Path("device/device_last_used/current.json"),
                self.client.fetch_device_last_used,
            ),
            (
                "race_predictions",
                Path("training/race_predictions/latest.json"),
                self.client.fetch_race_predictions,
            ),
        ]

        daily_specs: list[tuple[str, Path, Callable[[], Any]]] = [
            (
                "user_summary",
                Path("daily/user_summary") / f"{cdate}.json",
                lambda: self.client.fetch_user_summary(cdate),
            ),
            (
                "sleep",
                Path("daily/sleep") / f"{cdate}.json",
                lambda: self.client.fetch_sleep(cdate),
            ),
            (
                "stress",
                Path("daily/stress") / f"{cdate}.json",
                lambda: self.client.fetch_stress(cdate),
            ),
            (
                "body_battery",
                Path("daily/body_battery") / f"{cdate}.json",
                lambda: self.client.fetch_body_battery(cdate),
            ),
            (
                "resting_hr",
                Path("daily/resting_hr") / f"{cdate}.json",
                lambda: self.client.fetch_resting_hr(cdate),
            ),
            (
                "hrv",
                Path("daily/hrv") / f"{cdate}.json",
                lambda: self.client.fetch_hrv(cdate),
            ),
            (
                "spo2",
                Path("daily/spo2") / f"{cdate}.json",
                lambda: self.client.fetch_spo2(cdate),
            ),
            (
                "body_composition",
                Path("daily/body_composition") / f"{cdate}.json",
                lambda: self.client.fetch_body_composition(cdate),
            ),
            (
                "hydration",
                Path("daily/hydration") / f"{cdate}.json",
                lambda: self.client.fetch_hydration(cdate),
            ),
            (
                "nutrition_food_log",
                Path("daily/nutrition_food_log") / f"{cdate}.json",
                lambda: self.client.fetch_nutrition_food_log(cdate),
            ),
            (
                "nutrition_meals",
                Path("daily/nutrition_meals") / f"{cdate}.json",
                lambda: self.client.fetch_nutrition_meals(cdate),
            ),
            (
                "nutrition_settings",
                Path("daily/nutrition_settings") / f"{cdate}.json",
                lambda: self.client.fetch_nutrition_settings(cdate),
            ),
            (
                "training_readiness",
                Path("daily/training_readiness") / f"{cdate}.json",
                lambda: self.client.fetch_training_readiness(cdate),
            ),
            (
                "training_status",
                Path("daily/training_status") / f"{cdate}.json",
                lambda: self.client.fetch_training_status(cdate),
            ),
            (
                "activities",
                Path("daily/activities") / f"{cdate}.json",
                lambda: self.client.fetch_daily_activities(cdate),
            ),
        ]

        account_results: list[dict[str, Any]] = []
        if include_account_snapshots:
            for resource, relative_path, fetcher in account_specs:
                account_results.append(
                    self._sync_resource(
                        resource=resource,
                        relative_path=relative_path,
                        fetcher=fetcher,
                    )
                )

        daily_results: list[dict[str, Any]] = []
        for resource, relative_path, fetcher in daily_specs:
            daily_results.append(
                self._sync_resource(
                    resource=resource,
                    relative_path=relative_path,
                    fetcher=fetcher,
                )
            )

        errors = [
            *[item for item in account_results if item["status"] == "error"],
            *[item for item in daily_results if item["status"] == "error"],
        ]
        status = "partial" if errors else "success"
        finished_at = datetime.now(UTC).isoformat()
        report: dict[str, Any] = {
            "command": "sync-daily",
            "date": cdate,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": status,
            "account_resources": account_results,
            "daily_resources": daily_results,
            "error_count": len(errors),
        }
        report["report_path"] = self._save_report(
            command="sync-daily",
            started_at=started_at,
            finished_at=finished_at,
            report=report,
            status=status,
        )
        return report
