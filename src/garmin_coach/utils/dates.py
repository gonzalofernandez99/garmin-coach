"""Date helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta


def parse_iso_date(value: str) -> date:
    """Parse YYYY-MM-DD."""

    return date.fromisoformat(value)


def iso_date(value: date) -> str:
    """Format date as YYYY-MM-DD."""

    return value.isoformat()


def today_utc() -> date:
    """Return current UTC date."""

    return datetime.utcnow().date()


def inclusive_date_range(start: date, end: date) -> list[date]:
    """Return an inclusive list of dates."""

    if start > end:
        raise ValueError("start cannot be after end")
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]
