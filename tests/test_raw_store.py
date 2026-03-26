"""Tests for raw JSON storage."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from garmin_coach.storage.raw_store import RawJsonStore
from garmin_coach.storage.sqlite_store import SqliteIndex


class RawJsonStoreTest(unittest.TestCase):
    def test_save_json_skips_identical_payloads(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = RawJsonStore(
                root / "raw",
                SqliteIndex(root / "state" / "index.db"),
            )
            payload = {"steps": 1234, "date": "2026-03-24"}

            first = store.save_json("daily/user_summary/2026-03-24.json", payload)
            second = store.save_json("daily/user_summary/2026-03-24.json", payload)

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertEqual(first.sha256, second.sha256)

    def test_read_json_returns_saved_payload(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = RawJsonStore(root / "raw")
            payload = {"sleep": {"hours": 7.5}}

            store.save_json("daily/sleep/2026-03-24.json", payload)
            reloaded = store.read_json("daily/sleep/2026-03-24.json")

            self.assertEqual(reloaded, payload)


if __name__ == "__main__":
    unittest.main()
