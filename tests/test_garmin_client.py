"""Tests for Garmin client auth flow."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from garmin_coach.config import Settings
from garmin_coach.garmin_client import GarminCoachClient


class _FakeAuthError(Exception):
    pass


class _FakeConnectionError(Exception):
    pass


class _FakeTooManyRequestsError(Exception):
    pass


class _FakeGarth:
    def __init__(self) -> None:
        self.dump_calls: list[str] = []
        self._garth_home: str | None = None
        self.profile = {
            "displayName": "secret-user",
            "fullName": "Secret Name",
        }

    def dump(self, path: str) -> None:
        self.dump_calls.append(path)


class _FakeGarmin:
    instances: list["_FakeGarmin"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.login_calls: list[str | None] = []
        self.upload_calls: list[dict] = []
        self.schedule_calls: list[tuple[int | str, str]] = []
        self.garth = _FakeGarth()
        self.display_name = "secret-user"
        self.full_name = "Secret Name"
        self.unit_system = "metric"
        _FakeGarmin.instances.append(self)

    def login(self, tokenstore: str | None = None):
        self.login_calls.append(tokenstore)
        return None, None

    def upload_workout(self, workout_json):
        self.upload_calls.append(workout_json)
        return {"workoutId": 12345}

    def schedule_workout(self, workout_id, date_str):
        self.schedule_calls.append((workout_id, date_str))
        return {"scheduledWorkoutId": 98765, "date": date_str}


class _FakeDependencies:
    Garmin = _FakeGarmin
    auth_error = _FakeAuthError
    connection_error = _FakeConnectionError
    too_many_requests_error = _FakeTooManyRequestsError


def _build_settings(root: Path) -> Settings:
    data_dir = root / "data"
    return Settings(
        project_root=root,
        env_file=root / ".env",
        email="user@example.com",
        password="secret",
        tokenstore_path=root / ".secrets" / "garmin_tokens",
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        normalized_dir=data_dir / "normalized",
        summaries_dir=data_dir / "summaries",
        logs_dir=data_dir / "logs",
        sqlite_path=data_dir / "state" / "garmin_coach.db",
        region="global",
        log_level="INFO",
        retries=1,
        retry_backoff_seconds=0.0,
    )


class GarminCoachClientTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeGarmin.instances.clear()

    def test_login_without_existing_tokens_uses_credentials_and_persists(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()

            with patch(
                "garmin_coach.garmin_client.import_garmin_dependencies",
                return_value=_FakeDependencies(),
            ):
                client = GarminCoachClient(settings)
                api = client.login()

            self.assertEqual(api.login_calls, [None])
            self.assertEqual(
                api.garth.dump_calls,
                [str(settings.tokenstore_path)],
            )
            self.assertEqual(api.garth._garth_home, str(settings.tokenstore_path))

    def test_login_with_existing_tokens_uses_tokenstore(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            settings.tokenstore_path.mkdir(parents=True, exist_ok=True)
            (settings.tokenstore_path / "oauth1_token.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (settings.tokenstore_path / "oauth2_token.json").write_text(
                "{}",
                encoding="utf-8",
            )

            with patch(
                "garmin_coach.garmin_client.import_garmin_dependencies",
                return_value=_FakeDependencies(),
            ):
                client = GarminCoachClient(settings)
                api = client.login()

            self.assertEqual(api.login_calls, [str(settings.tokenstore_path)])
            self.assertEqual(api.garth.dump_calls, [])

    def test_login_test_redacts_profile_identity_fields(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()

            with patch(
                "garmin_coach.garmin_client.import_garmin_dependencies",
                return_value=_FakeDependencies(),
            ):
                client = GarminCoachClient(settings)
                payload = client.login_test()

            self.assertTrue(payload["authenticated"])
            self.assertTrue(payload["account_summary"]["profile_available"])
            self.assertTrue(payload["account_summary"]["display_name_present"])
            self.assertTrue(payload["account_summary"]["full_name_present"])
            self.assertNotIn("profile", payload)
            self.assertNotIn("display_name", payload)
            self.assertNotIn("full_name", payload)
            self.assertNotIn("tokenstore_path", payload)

    def test_upload_workout_uses_underlying_api(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()

            with patch(
                "garmin_coach.garmin_client.import_garmin_dependencies",
                return_value=_FakeDependencies(),
            ):
                client = GarminCoachClient(settings)
                api = client.login()
                response = client.upload_workout({"workoutName": "Run 5x1000"})

            self.assertEqual(api.upload_calls, [{"workoutName": "Run 5x1000"}])
            self.assertEqual(response["workoutId"], 12345)

    def test_schedule_workout_uses_underlying_api(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()

            with patch(
                "garmin_coach.garmin_client.import_garmin_dependencies",
                return_value=_FakeDependencies(),
            ):
                client = GarminCoachClient(settings)
                api = client.login()
                response = client.schedule_workout(12345, "2026-03-28")

            self.assertEqual(api.schedule_calls, [(12345, "2026-03-28")])
            self.assertEqual(response["scheduledWorkoutId"], 98765)


if __name__ == "__main__":
    unittest.main()
