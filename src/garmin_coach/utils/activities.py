"""Activity parsing helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def extract_activity_id(activity: dict[str, Any]) -> str | None:
    """Extract an activity identifier from common Garmin payload shapes."""

    for key in ("activityId", "activityUUID", "id"):
        value = activity.get(key)
        if value is not None:
            return str(value)
    summary = activity.get("summaryDTO")
    if isinstance(summary, dict):
        for key in ("activityId", "activityUUID", "id"):
            value = summary.get(key)
            if value is not None:
                return str(value)
    return None


def _parse_datetime(value: str) -> datetime | None:
    normalized = value.strip().replace("Z", "+00:00")
    for candidate in (
        normalized,
        normalized.replace(" ", "T"),
        normalized.split(".")[0].replace(" ", "T"),
    ):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def extract_activity_start(activity: dict[str, Any]) -> datetime | None:
    """Extract the local or GMT activity start timestamp."""

    candidate_fields = ("startTimeLocal", "startTimeGMT", "activityDate")
    for field in candidate_fields:
        value = activity.get(field)
        if isinstance(value, str):
            parsed = _parse_datetime(value)
            if parsed is not None:
                return parsed

    summary = activity.get("summaryDTO")
    if isinstance(summary, dict):
        for field in candidate_fields:
            value = summary.get(field)
            if isinstance(value, str):
                parsed = _parse_datetime(value)
                if parsed is not None:
                    return parsed
    return None


def dedupe_activities(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first occurrence of each activity id."""

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for activity in activities:
        activity_id = extract_activity_id(activity)
        if activity_id is None or activity_id in seen:
            continue
        seen.add(activity_id)
        deduped.append(activity)
    return deduped


def activity_list_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Extract a list of activities from common Garmin payload shapes."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("activities", "activityList", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []
