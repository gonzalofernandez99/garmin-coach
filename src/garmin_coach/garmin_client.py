"""Thin wrapper around python-garminconnect with retries and fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import time
from typing import Any, Callable

from pathlib import Path

from .config import Settings, tokenstore_has_tokens, validate_auth_configuration
from .exceptions import DependencyError, ResourceUnavailableError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GarminDependencies:
    """Imported garminconnect runtime symbols."""

    Garmin: type
    auth_error: type[Exception]
    connection_error: type[Exception]
    too_many_requests_error: type[Exception]


def import_garmin_dependencies() -> GarminDependencies:
    """Import garminconnect lazily so tests can run without it installed."""

    try:
        from garminconnect import (
            Garmin,
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
            GarminConnectTooManyRequestsError,
        )
    except ImportError as exc:
        raise DependencyError(
            "Missing dependency 'garminconnect'. Install the project with `pip install -e .`."
        ) from exc

    return GarminDependencies(
        Garmin=Garmin,
        auth_error=GarminConnectAuthenticationError,
        connection_error=GarminConnectConnectionError,
        too_many_requests_error=GarminConnectTooManyRequestsError,
    )


class GarminCoachClient:
    """Stateful Garmin client with light resilience around the upstream wrapper."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dependencies = import_garmin_dependencies()
        self._api: Any | None = None

    def _prompt_mfa(self) -> str:
        return input("Garmin MFA code: ").strip()

    def _is_auth_error(self, exc: Exception) -> bool:
        return isinstance(exc, self.dependencies.auth_error)

    def _tokenstore_has_tokens(self) -> bool:
        return tokenstore_has_tokens(self.settings.tokenstore_path)

    def _persist_tokens(self, api: Any) -> None:
        tokenstore_path = self.settings.tokenstore_path
        tokenstore_path.mkdir(parents=True, exist_ok=True)
        api.garth.dump(str(tokenstore_path))
        api.garth._garth_home = str(tokenstore_path)

    def _call_with_retries(self, operation_name: str, func: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        retryable = (
            self.dependencies.connection_error,
            self.dependencies.too_many_requests_error,
        )

        for attempt in range(1, self.settings.retries + 1):
            try:
                return func()
            except self.dependencies.auth_error:
                raise
            except retryable as exc:
                last_error = exc
                if attempt >= self.settings.retries:
                    break
                sleep_seconds = self.settings.retry_backoff_seconds * attempt
                logger.warning(
                    "Retrying Garmin operation %s after error (%s/%s): %s",
                    operation_name,
                    attempt,
                    self.settings.retries,
                    exc,
                )
                time.sleep(sleep_seconds)

        if last_error is not None:
            raise last_error
        return func()

    def login(self) -> Any:
        """Authenticate and cache the upstream Garmin API client."""

        if self._api is not None:
            return self._api

        validate_auth_configuration(self.settings)
        api = self.dependencies.Garmin(
            email=self.settings.email,
            password=self.settings.password,
            is_cn=self.settings.region == "cn",
            prompt_mfa=self._prompt_mfa,
        )

        if self._tokenstore_has_tokens():
            self._call_with_retries(
                "login",
                lambda: api.login(tokenstore=str(self.settings.tokenstore_path)),
            )
        else:
            self._call_with_retries("login", lambda: api.login())
            self._persist_tokens(api)

        self._api = api
        return api

    def _api_call_variants(
        self,
        resource_name: str,
        calls: list[Callable[[Any], Any]],
    ) -> Any:
        api = self.login()
        last_error: Exception | None = None

        for call in calls:
            try:
                return self._call_with_retries(resource_name, lambda call=call: call(api))
            except (AttributeError, TypeError) as exc:
                last_error = exc
                continue
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise
                last_error = exc
                logger.debug("Variant failed for %s: %s", resource_name, exc)
                continue

        raise ResourceUnavailableError(
            f"Unable to fetch Garmin resource '{resource_name}'."
        ) from last_error

    def _display_name(self) -> str:
        api = self.login()
        if getattr(api, "display_name", None):
            return str(api.display_name)

        profile = getattr(getattr(api, "garth", None), "profile", None)
        if isinstance(profile, dict):
            for field in ("displayName", "username"):
                value = profile.get(field)
                if value:
                    return str(value)

        raise ResourceUnavailableError("Garmin display name is not available after login.")

    def login_test(self) -> dict[str, Any]:
        """Authenticate and return basic account metadata."""

        api = self.login()
        profile = self.fetch_profile()
        return {
            "authenticated_at": datetime.now(UTC).isoformat(),
            "authenticated": True,
            "region": self.settings.region,
            "tokenstore_present": self._tokenstore_has_tokens(),
            "account_summary": {
                "unit_system": getattr(api, "unit_system", None),
                "profile_available": isinstance(profile, dict) and bool(profile),
                "display_name_present": bool(getattr(api, "display_name", None)),
                "full_name_present": bool(getattr(api, "full_name", None)),
            },
            "privacy_notice": "PII omitted from login-test output.",
        }

    def fetch_profile(self) -> dict[str, Any]:
        """Return basic Garmin profile info."""

        api = self.login()
        profile = getattr(getattr(api, "garth", None), "profile", None)
        if isinstance(profile, dict) and profile:
            return profile
        return self._api_call_variants(
            "profile",
            [
                lambda api: api.connectapi("/userprofile-service/userprofile/profile"),
            ],
        )

    def fetch_profile_settings(self) -> dict[str, Any]:
        return self._api_call_variants(
            "profile_settings",
            [
                lambda api: api.connectapi("/userprofile-service/userprofile/settings"),
            ],
        )

    def fetch_user_settings(self) -> dict[str, Any]:
        return self._api_call_variants(
            "user_settings",
            [
                lambda api: api.connectapi(
                    "/userprofile-service/userprofile/user-settings"
                ),
            ],
        )

    def fetch_devices(self) -> list[dict[str, Any]] | dict[str, Any]:
        return self._api_call_variants(
            "devices",
            [
                lambda api: api.get_devices(),
                lambda api: api.connectapi("/device-service/deviceregistration/devices"),
            ],
        )

    def fetch_primary_training_device(self) -> dict[str, Any]:
        return self._api_call_variants(
            "primary_training_device",
            [
                lambda api: api.get_primary_training_device(),
                lambda api: api.connectapi("/web-gateway/device-info/primary-training-device"),
            ],
        )

    def fetch_device_last_used(self) -> dict[str, Any]:
        return self._api_call_variants(
            "device_last_used",
            [
                lambda api: api.get_device_last_used(),
                lambda api: api.connectapi("/device-service/deviceservice/mylastused"),
            ],
        )

    def fetch_race_predictions(self) -> dict[str, Any]:
        display_name = self._display_name()
        return self._api_call_variants(
            "race_predictions",
            [
                lambda api: api.get_race_predictions(),
                lambda api: api.connectapi(
                    f"/metrics-service/metrics/racepredictions/latest/{display_name}"
                ),
            ],
        )

    def fetch_user_summary(self, cdate: str) -> dict[str, Any]:
        display_name = self._display_name()
        return self._api_call_variants(
            "user_summary",
            [
                lambda api: api.get_user_summary(cdate),
                lambda api: api.get_stats(cdate),
                lambda api: api.connectapi(
                    f"/usersummary-service/usersummary/daily/{display_name}",
                    params={"calendarDate": cdate},
                ),
            ],
        )

    def fetch_sleep(self, cdate: str) -> dict[str, Any]:
        display_name = self._display_name()
        return self._api_call_variants(
            "sleep",
            [
                lambda api: api.get_sleep_data(cdate),
                lambda api: api.get_daily_sleep_data(cdate),
                lambda api: api.connectapi(
                    f"/wellness-service/wellness/dailySleepData/{display_name}",
                    params={"date": cdate, "nonSleepBufferMinutes": 60},
                ),
            ],
        )

    def fetch_stress(self, cdate: str) -> dict[str, Any]:
        display_name = self._display_name()
        return self._api_call_variants(
            "stress",
            [
                lambda api: api.get_stress_data(cdate),
                lambda api: api.get_stress(cdate),
                lambda api: api.connectapi(
                    f"/wellness-service/wellness/dailyStress/{display_name}",
                    params={"date": cdate},
                ),
            ],
        )

    def fetch_body_battery(self, cdate: str) -> dict[str, Any]:
        display_name = self._display_name()
        return self._api_call_variants(
            "body_battery",
            [
                lambda api: api.get_body_battery(cdate),
                lambda api: api.get_body_battery_data(cdate),
                lambda api: api.connectapi(
                    f"/wellness-service/wellness/bodyBattery/reports/daily/{display_name}",
                    params={"date": cdate},
                ),
                lambda api: api.connectapi(
                    "/wellness-service/wellness/bodyBattery/reports/daily",
                    params={"date": cdate},
                ),
            ],
        )

    def fetch_resting_hr(self, cdate: str) -> dict[str, Any] | list[dict[str, Any]]:
        return self._api_call_variants(
            "resting_hr",
            [
                lambda api: api.get_rhr_day(cdate),
                lambda api: api.get_resting_heart_rate(cdate),
                lambda api: api.connectapi(f"/userstats-service/wellness/daily/{cdate}"),
            ],
        )

    def fetch_hrv(self, cdate: str) -> dict[str, Any] | list[dict[str, Any]]:
        return self._api_call_variants(
            "hrv",
            [
                lambda api: api.get_hrv_data(cdate),
                lambda api: api.get_hrv(cdate),
                lambda api: api.connectapi(f"/hrv-service/hrv/{cdate}"),
                lambda api: api.connectapi(
                    "/hrv-service/hrv",
                    params={"fromDate": cdate, "untilDate": cdate},
                ),
            ],
        )

    def fetch_spo2(self, cdate: str) -> dict[str, Any] | list[dict[str, Any]]:
        display_name = self._display_name()
        return self._api_call_variants(
            "spo2",
            [
                lambda api: api.get_spo2_data(cdate),
                lambda api: api.get_daily_spo2_data(cdate),
                lambda api: api.connectapi(
                    f"/wellness-service/wellness/daily/spo2/{display_name}",
                    params={"date": cdate},
                ),
                lambda api: api.connectapi(
                    "/wellness-service/wellness/daily/spo2",
                    params={"date": cdate},
                ),
            ],
        )

    def fetch_body_composition(self, cdate: str) -> dict[str, Any]:
        return self._api_call_variants(
            "body_composition",
            [
                lambda api: api.get_body_composition(cdate),
                lambda api: api.get_stats_and_body(cdate),
            ],
        )

    def fetch_hydration(self, cdate: str) -> dict[str, Any]:
        return self._api_call_variants(
            "hydration",
            [
                lambda api: api.get_hydration_data(cdate),
                lambda api: api.get_daily_hydration_data(cdate),
                lambda api: api.connectapi(
                    f"/usersummary-service/usersummary/hydration/daily/{cdate}"
                ),
            ],
        )

    def fetch_nutrition_food_log(self, cdate: str) -> dict[str, Any]:
        return self._api_call_variants(
            "nutrition_food_log",
            [
                lambda api: api.get_nutrition_daily_food_log(cdate),
                lambda api: api.connectapi(f"/nutrition-service/food/logs/{cdate}"),
            ],
        )

    def fetch_nutrition_meals(self, cdate: str) -> dict[str, Any]:
        return self._api_call_variants(
            "nutrition_meals",
            [
                lambda api: api.get_nutrition_daily_meals(cdate),
                lambda api: api.connectapi(f"/nutrition-service/meals/{cdate}"),
            ],
        )

    def fetch_nutrition_settings(self, cdate: str) -> dict[str, Any]:
        return self._api_call_variants(
            "nutrition_settings",
            [
                lambda api: api.get_nutrition_daily_settings(cdate),
                lambda api: api.connectapi(f"/nutrition-service/settings/{cdate}"),
            ],
        )

    def fetch_training_readiness(self, cdate: str) -> dict[str, Any]:
        display_name = self._display_name()
        return self._api_call_variants(
            "training_readiness",
            [
                lambda api: api.get_training_readiness(cdate),
                lambda api: api.connectapi(
                    f"/metrics-service/metrics/trainingreadiness/{cdate}"
                ),
                lambda api: api.connectapi(
                    "/metrics-service/metrics/trainingreadiness",
                    params={"calendarDate": cdate},
                ),
                lambda api: api.connectapi(
                    f"/metrics-service/metrics/trainingreadiness/{display_name}",
                    params={"calendarDate": cdate},
                ),
            ],
        )

    def fetch_training_status(self, cdate: str) -> dict[str, Any]:
        return self._api_call_variants(
            "training_status",
            [
                lambda api: api.get_training_status(cdate),
                lambda api: api.connectapi(
                    f"/metrics-service/metrics/trainingstatus/aggregated/{cdate}"
                ),
            ],
        )

    def fetch_daily_activities(self, cdate: str) -> list[dict[str, Any]] | dict[str, Any]:
        display_name = self._display_name()
        return self._api_call_variants(
            "daily_activities",
            [
                lambda api: api.get_activities_by_date(cdate),
                lambda api: api.get_activities_by_date(cdate, cdate),
                lambda api: api.connectapi(
                    f"/activitylist-service/activities/fordailysummary/{display_name}",
                    params={"calendarDate": cdate},
                ),
            ],
        )

    def fetch_activity_summary(self, activity_id: str) -> dict[str, Any]:
        return self._api_call_variants(
            "activity_summary",
            [
                lambda api: api.get_activity(activity_id),
            ],
        )

    def fetch_activity_details(self, activity_id: str) -> dict[str, Any]:
        return self._api_call_variants(
            "activity_details",
            [
                lambda api: api.get_activity_details(activity_id),
            ],
        )

    def fetch_activity_splits(self, activity_id: str) -> dict[str, Any]:
        return self._api_call_variants(
            "activity_splits",
            [
                lambda api: api.get_activity_splits(activity_id),
            ],
        )

    def fetch_activity_typed_splits(self, activity_id: str) -> dict[str, Any]:
        return self._api_call_variants(
            "activity_typed_splits",
            [
                lambda api: api.get_activity_typed_splits(activity_id),
            ],
        )

    def fetch_activity_split_summaries(self, activity_id: str) -> dict[str, Any]:
        return self._api_call_variants(
            "activity_split_summaries",
            [
                lambda api: api.get_activity_split_summaries(activity_id),
            ],
        )

    def upload_workout(self, workout_json: dict[str, Any]) -> dict[str, Any]:
        """Upload a Garmin workout payload."""

        return self._api_call_variants(
            "upload_workout",
            [
                lambda api: api.upload_workout(workout_json),
            ],
        )

    def schedule_workout(self, workout_id: int | str, date_str: str) -> dict[str, Any]:
        """Schedule an uploaded workout in Garmin Connect."""

        return self._api_call_variants(
            "schedule_workout",
            [
                lambda api: api.schedule_workout(workout_id, date_str),
            ],
        )
