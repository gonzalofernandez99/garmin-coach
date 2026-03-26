"""Configuration loading and runtime paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from .env import load_dotenv
from .exceptions import ConfigurationError


def tokenstore_has_tokens(tokenstore_path: Path) -> bool:
    """Return whether a Garmin tokenstore contains the expected token files."""

    if not tokenstore_path.exists() or not tokenstore_path.is_dir():
        return False
    required_files = ("oauth1_token.json", "oauth2_token.json")
    return all((tokenstore_path / filename).exists() for filename in required_files)


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
def _to_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def _to_float(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    return float(value)


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment."""

    project_root: Path
    env_file: Path
    email: str | None
    password: str | None
    tokenstore_path: Path
    data_dir: Path
    raw_dir: Path
    normalized_dir: Path
    summaries_dir: Path
    logs_dir: Path
    sqlite_path: Path
    region: str
    log_level: str
    retries: int
    retry_backoff_seconds: float
    coach_recalibration_days: int = 21

    def ensure_runtime_dirs(self) -> None:
        """Create local directories used by the project."""

        for path in (
            self.data_dir,
            self.raw_dir,
            self.normalized_dir,
            self.summaries_dir,
            self.logs_dir,
            self.sqlite_path.parent,
            self.tokenstore_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load settings from .env and process environment."""

    project_root = Path.cwd()
    resolved_env = project_root / ".env" if env_file is None else Path(env_file)
    load_dotenv(resolved_env)

    data_dir = Path(os.getenv("GARMIN_DATA_DIR", "data")).expanduser()
    sqlite_path = Path(
        os.getenv("GARMIN_SQLITE_PATH", str(data_dir / "state" / "garmin_coach.db"))
    ).expanduser()
    tokenstore_path = Path(
        os.getenv("GARMIN_TOKENSTORE", ".secrets/garmin_tokens")
    ).expanduser()

    settings = Settings(
        project_root=project_root,
        env_file=resolved_env,
        email=os.getenv("GARMIN_EMAIL"),
        password=os.getenv("GARMIN_PASSWORD"),
        tokenstore_path=tokenstore_path,
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        normalized_dir=data_dir / "normalized",
        summaries_dir=data_dir / "summaries",
        logs_dir=data_dir / "logs",
        sqlite_path=sqlite_path,
        region=os.getenv("GARMIN_REGION", "global").strip().lower(),
        log_level=os.getenv("GARMIN_LOG_LEVEL", "INFO").strip().upper(),
        retries=_to_int(os.getenv("GARMIN_RETRIES"), 3),
        retry_backoff_seconds=_to_float(
            os.getenv("GARMIN_RETRY_BACKOFF_SECONDS"), 1.5
        ),
        coach_recalibration_days=_to_int(
            os.getenv("GARMIN_COACH_RECALIBRATION_DAYS"),
            21,
        ),
    )
    settings.ensure_runtime_dirs()
    return settings


def validate_auth_configuration(settings: Settings) -> None:
    """Ensure there is at least one auth path available."""

    has_credentials = bool(settings.email and settings.password)
    has_saved_tokens = tokenstore_has_tokens(settings.tokenstore_path)
    if has_credentials or has_saved_tokens:
        return
    raise ConfigurationError(
        "Missing Garmin authentication. Set GARMIN_EMAIL and GARMIN_PASSWORD in .env "
        "or reuse an existing GARMIN_TOKENSTORE."
    )
