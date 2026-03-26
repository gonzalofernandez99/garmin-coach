"""Logging configuration helpers."""

from __future__ import annotations

import logging

from .config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure console and file logging for the application."""

    root = logging.getLogger()
    level = getattr(logging, settings.log_level, logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not root.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    file_handler_present = any(
        isinstance(handler, logging.FileHandler) for handler in root.handlers
    )
    if not file_handler_present:
        file_handler = logging.FileHandler(
            settings.logs_dir / "garmin-coach.log",
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    logging.getLogger("garminconnect").setLevel(logging.WARNING)
