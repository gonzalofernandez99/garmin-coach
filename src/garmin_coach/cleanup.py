"""Maintenance helpers for pruning generated JSON artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Settings
from .storage.sqlite_store import SqliteIndex


class JsonCleanupService:
    """Delete generated JSON artifacts under the project data directories."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sqlite_index = SqliteIndex(settings.sqlite_path)

    def _roots_for_scope(self, scope: str) -> list[tuple[str, Path]]:
        if scope == "raw":
            return [("raw", self.settings.raw_dir)]
        if scope == "normalized":
            return [("normalized", self.settings.normalized_dir)]
        if scope == "summaries":
            return [("summaries", self.settings.summaries_dir)]
        if scope == "all":
            return [
                ("raw", self.settings.raw_dir),
                ("normalized", self.settings.normalized_dir),
                ("summaries", self.settings.summaries_dir),
            ]
        raise ValueError(f"Unsupported cleanup scope '{scope}'.")

    def _json_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        return sorted(path for path in root.rglob("*.json") if path.is_file())

    def _prune_empty_dirs(self, root: Path) -> int:
        if not root.exists():
            return 0
        removed = 0
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if any(directory.iterdir()):
                continue
            directory.rmdir()
            removed += 1
        return removed

    def purge_json(self, *, scope: str = "all", dry_run: bool = False) -> dict[str, Any]:
        """Delete JSON files under the selected data scope and report the result."""

        roots = self._roots_for_scope(scope)
        files_by_scope = {
            label: self._json_files(root)
            for label, root in roots
        }
        raw_relative_paths = [
            path.relative_to(self.settings.raw_dir).as_posix()
            for path in files_by_scope.get("raw", [])
        ]

        deleted_by_scope: dict[str, int] = {
            label: len(paths)
            for label, paths in files_by_scope.items()
        }
        deleted_files = sum(deleted_by_scope.values())
        deleted_raw_records = 0
        pruned_directories = 0

        if not dry_run:
            for paths in files_by_scope.values():
                for path in paths:
                    path.unlink(missing_ok=True)

            if raw_relative_paths:
                deleted_raw_records = self.sqlite_index.delete_raw_records(raw_relative_paths)

            for _, root in roots:
                pruned_directories += self._prune_empty_dirs(root)

        return {
            "scope": scope,
            "dry_run": dry_run,
            "deleted_files": deleted_files,
            "deleted_by_scope": deleted_by_scope,
            "deleted_raw_records": deleted_raw_records,
            "pruned_directories": pruned_directories,
            "roots": {
                label: str(root)
                for label, root in roots
            },
        }
