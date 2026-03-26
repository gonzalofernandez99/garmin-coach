"""Tests for JSON cleanup maintenance commands."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from garmin_coach.cleanup import JsonCleanupService
from garmin_coach.config import Settings
from garmin_coach.storage.raw_store import RawJsonStore
from garmin_coach.storage.sqlite_store import SqliteIndex


def _build_settings(root: Path) -> Settings:
    data_dir = root / "data"
    return Settings(
        project_root=root,
        env_file=root / ".env",
        email=None,
        password=None,
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


class JsonCleanupServiceTest(unittest.TestCase):
    def test_dry_run_reports_files_without_deleting(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            raw_store = RawJsonStore(settings.raw_dir, SqliteIndex(settings.sqlite_path))
            normalized_store = RawJsonStore(settings.normalized_dir)
            summaries_store = RawJsonStore(settings.summaries_dir)

            raw_store.save_json("daily/user_summary/2026-03-24.json", {"ok": True})
            normalized_store.save_json("coach/athlete_profile/current.json", {"ok": True})
            summaries_store.save_json("coach/exports/medium/latest.json", {"ok": True})

            service = JsonCleanupService(settings)
            report = service.purge_json(scope="all", dry_run=True)

            self.assertEqual(report["deleted_files"], 3)
            self.assertEqual(report["deleted_raw_records"], 0)
            self.assertTrue((settings.raw_dir / "daily/user_summary/2026-03-24.json").exists())
            self.assertTrue((settings.normalized_dir / "coach/athlete_profile/current.json").exists())
            self.assertTrue((settings.summaries_dir / "coach/exports/medium/latest.json").exists())

    def test_purge_deletes_files_and_clears_raw_hashes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            sqlite_index = SqliteIndex(settings.sqlite_path)
            raw_store = RawJsonStore(settings.raw_dir, sqlite_index)
            normalized_store = RawJsonStore(settings.normalized_dir)
            summaries_store = RawJsonStore(settings.summaries_dir)

            raw_store.save_json("daily/user_summary/2026-03-24.json", {"ok": True})
            raw_store.save_json("training/race_predictions/latest.json", {"ok": True})
            normalized_store.save_json("coach/athlete_profile/current.json", {"ok": True})
            summaries_store.save_json("coach/exports/medium/latest.json", {"ok": True})

            service = JsonCleanupService(settings)
            report = service.purge_json(scope="all", dry_run=False)

            self.assertEqual(report["deleted_files"], 4)
            self.assertEqual(report["deleted_raw_records"], 2)
            self.assertFalse((settings.raw_dir / "daily/user_summary/2026-03-24.json").exists())
            self.assertFalse((settings.raw_dir / "training/race_predictions/latest.json").exists())
            self.assertFalse((settings.normalized_dir / "coach/athlete_profile/current.json").exists())
            self.assertFalse((settings.summaries_dir / "coach/exports/medium/latest.json").exists())
            self.assertIsNone(sqlite_index.get_hash("daily/user_summary/2026-03-24.json"))
            self.assertIsNone(sqlite_index.get_hash("training/race_predictions/latest.json"))


if __name__ == "__main__":
    unittest.main()
