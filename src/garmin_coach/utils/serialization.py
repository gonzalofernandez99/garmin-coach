"""Stable JSON serialization helpers."""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


def _default_json(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def stable_json_dumps(payload: Any) -> str:
    """Serialize to deterministic JSON."""

    return json.dumps(
        payload,
        default=_default_json,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"


def payload_sha256(payload: Any) -> tuple[str, str]:
    """Return the serialized payload and its sha256 hash."""

    serialized = stable_json_dumps(payload)
    digest = sha256(serialized.encode("utf-8")).hexdigest()
    return serialized, digest
