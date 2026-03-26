"""Minimal .env loader without extra dependencies."""

from __future__ import annotations

from pathlib import Path
import os


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_dotenv(dotenv_path: Path | None) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from a .env file into the process env."""

    if dotenv_path is None or not dotenv_path.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        os.environ.setdefault(key, value)
        loaded[key] = value
    return loaded
