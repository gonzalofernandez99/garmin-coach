"""Raw JSON artifact storage."""

from __future__ import annotations

from datetime import datetime, UTC
import json
from pathlib import Path
from typing import Any

from ..models import SaveResult
from ..utils.serialization import payload_sha256
from .sqlite_store import SqliteIndex


class RawJsonStore:
    """Persist deterministic raw JSON artifacts to disk."""

    def __init__(self, base_dir: Path, sqlite_index: SqliteIndex | None = None) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_index = sqlite_index

    def _resolve_relative_path(self, relative_path: str | Path) -> Path:
        normalized = Path(relative_path)
        if normalized.is_absolute():
            raise ValueError("relative_path must be relative")
        return normalized

    def _existing_hash(self, relative_path: Path, absolute_path: Path) -> str | None:
        if self.sqlite_index is not None:
            return self.sqlite_index.get_hash(relative_path.as_posix())
        if not absolute_path.exists():
            return None
        serialized = absolute_path.read_text(encoding="utf-8")
        return payload_sha256(json.loads(serialized))[1]

    def save_json(self, relative_path: str | Path, payload: Any) -> SaveResult:
        """Save a JSON payload if it changed since the last write."""

        rel_path = self._resolve_relative_path(relative_path)
        abs_path = self.base_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        serialized, digest = payload_sha256(payload)
        existing_digest = self._existing_hash(rel_path, abs_path)
        changed = existing_digest != digest

        if changed:
            tmp_path = abs_path.with_name(f"{abs_path.name}.tmp")
            tmp_path.write_text(serialized, encoding="utf-8")
            tmp_path.replace(abs_path)

        if self.sqlite_index is not None:
            self.sqlite_index.upsert_raw_record(
                relative_path=rel_path.as_posix(),
                absolute_path=abs_path,
                sha256=digest,
                updated_at=datetime.now(UTC).isoformat(),
            )

        return SaveResult(path=abs_path, sha256=digest, changed=changed)

    def read_json(self, relative_path: str | Path) -> Any:
        """Read a saved raw JSON artifact."""

        rel_path = self._resolve_relative_path(relative_path)
        abs_path = self.base_dir / rel_path
        return json.loads(abs_path.read_text(encoding="utf-8"))
