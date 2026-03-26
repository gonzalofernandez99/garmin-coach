"""Shared dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SaveResult:
    """Result of writing a JSON artifact."""

    path: Path
    sha256: str
    changed: bool
