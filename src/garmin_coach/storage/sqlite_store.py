"""SQLite metadata store used to avoid duplicate raw writes."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any


class SqliteIndex:
    """Small SQLite store for artifact hashes and sync reports."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS raw_records (
                    relative_path TEXT PRIMARY KEY,
                    absolute_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )

    def get_hash(self, relative_path: str) -> str | None:
        """Return the last known hash for a raw artifact."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT sha256 FROM raw_records WHERE relative_path = ?",
                (relative_path,),
            ).fetchone()
        return None if row is None else str(row[0])

    def upsert_raw_record(
        self,
        *,
        relative_path: str,
        absolute_path: Path,
        sha256: str,
        updated_at: str,
    ) -> None:
        """Insert or update raw artifact metadata."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO raw_records (relative_path, absolute_path, sha256, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    absolute_path = excluded.absolute_path,
                    sha256 = excluded.sha256,
                    updated_at = excluded.updated_at
                """,
                (relative_path, str(absolute_path), sha256, updated_at),
            )

    def log_sync_run(
        self,
        *,
        command: str,
        started_at: str,
        finished_at: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        """Persist a sync execution report."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_runs (command, started_at, finished_at, status, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    command,
                    started_at,
                    finished_at,
                    status,
                    json.dumps(details, ensure_ascii=True, sort_keys=True),
                ),
            )

    def delete_raw_records(self, relative_paths: list[str]) -> int:
        """Delete raw metadata records for the given relative JSON paths."""

        if not relative_paths:
            return 0
        placeholders = ", ".join("?" for _ in relative_paths)
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM raw_records WHERE relative_path IN ({placeholders})",
                tuple(relative_paths),
            )
        return int(cursor.rowcount or 0)
