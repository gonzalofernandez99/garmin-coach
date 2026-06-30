"""Command line interface for garmin-coach."""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
from typing import Any

from .cleanup import JsonCleanupService
from .coach.service import CoachService
from .config import load_settings
from .exceptions import GarminCoachError
from .garmin_client import GarminCoachClient
from .logging_utils import configure_logging
from .storage.raw_store import RawJsonStore
from .storage.sqlite_store import SqliteIndex
from .sync.activities import ActivitySyncService
from .sync.daily import DailySyncService
from .utils.dates import parse_iso_date, today_utc
from .workouts.cycling import CyclingWorkoutService
from .workouts.running import RunningWorkoutService


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True))


def _summarize_workout_upload_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"uploaded": True}
    sport_type = payload.get("sportType")
    sport_type_key = sport_type.get("sportTypeKey") if isinstance(sport_type, dict) else None
    return {
        "workout_id": payload.get("workoutId") or payload.get("id"),
        "workout_name": payload.get("workoutName") or payload.get("name"),
        "sport_type": sport_type_key,
        "created_date": payload.get("createdDate"),
        "updated_date": payload.get("updatedDate"),
        "estimated_duration_in_secs": payload.get("estimatedDurationInSecs"),
        "estimated_distance_in_meters": payload.get("estimatedDistanceInMeters"),
    }


def _summarize_schedule_response(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"scheduled": True}
    return {
        "scheduled_workout_id": payload.get("scheduledWorkoutId") or payload.get("id"),
        "date": payload.get("date"),
    }


def _build_services(env_file: str | None) -> tuple[GarminCoachClient, DailySyncService, ActivitySyncService]:
    settings = load_settings(env_file=env_file)
    configure_logging(settings)
    sqlite_index = SqliteIndex(settings.sqlite_path)
    store = RawJsonStore(settings.raw_dir, sqlite_index)
    client = GarminCoachClient(settings)
    daily_sync = DailySyncService(client, store)
    activity_sync = ActivitySyncService(client, store, daily_sync)
    return client, daily_sync, activity_sync


def _build_coach_service(env_file: str | None) -> CoachService:
    settings = load_settings(env_file=env_file)
    configure_logging(settings)
    return CoachService(settings)


def _build_cleanup_service(env_file: str | None) -> JsonCleanupService:
    settings = load_settings(env_file=env_file)
    configure_logging(settings)
    return JsonCleanupService(settings)


def _build_running_workout_service(
    env_file: str | None,
) -> tuple[RunningWorkoutService, GarminCoachClient]:
    settings = load_settings(env_file=env_file)
    configure_logging(settings)
    return RunningWorkoutService(settings), GarminCoachClient(settings)


def _build_cycling_workout_service(
    env_file: str | None,
) -> tuple[CyclingWorkoutService, GarminCoachClient]:
    settings = load_settings(env_file=env_file)
    configure_logging(settings)
    return CyclingWorkoutService(settings), GarminCoachClient(settings)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--env-file",
        default=None,
        help="Path to a .env file. Defaults to ./.env",
    )

    parser = argparse.ArgumentParser(prog="garmin-coach")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("login-test", parents=[parent], help="Validate Garmin auth")

    sync_daily = subparsers.add_parser(
        "sync-daily",
        parents=[parent],
        help="Sync one date of raw Garmin data",
    )
    sync_daily.add_argument(
        "--date",
        default=today_utc().isoformat(),
        help="Date in YYYY-MM-DD format. Defaults to today in UTC.",
    )
    sync_daily.add_argument(
        "--build-exports",
        action="store_true",
        help="Also build generic exports after the sync finishes.",
    )
    sync_daily.add_argument(
        "--export-level",
        choices=("low", "medium", "full", "all"),
        default="all",
        help="Export level used with --build-exports. Defaults to all.",
    )
    sync_daily.add_argument(
        "--build-activity-summaries",
        action="store_true",
        help="Also build per-activity summaries after the sync finishes.",
    )

    sync_last = subparsers.add_parser(
        "sync-last-30-days",
        parents=[parent],
        help="Sync recent daily data and activity details",
    )
    sync_last.add_argument(
        "--end-date",
        default=today_utc().isoformat(),
        help="Window end date in YYYY-MM-DD format. Defaults to today in UTC.",
    )
    sync_last.add_argument(
        "--days",
        type=int,
        default=30,
        help="Window size in days. Defaults to 30.",
    )
    sync_last.add_argument(
        "--build-exports",
        action="store_true",
        help="Also build generic exports after the sync finishes.",
    )
    sync_last.add_argument(
        "--export-level",
        choices=("low", "medium", "full", "all"),
        default="all",
        help="Export level used with --build-exports. Defaults to all.",
    )
    sync_last.add_argument(
        "--build-activity-summaries",
        action="store_true",
        help="Also build per-activity summaries after the sync finishes.",
    )

    coach_context = subparsers.add_parser(
        "coach-build-context",
        parents=[parent],
        help="Build the normalized athlete profile and coach packet",
    )
    coach_context.add_argument(
        "--date",
        default=None,
        help="Optional date in YYYY-MM-DD format. Defaults to latest available Garmin date.",
    )

    coach_exports = subparsers.add_parser(
        "coach-build-exports",
        parents=[parent],
        help="Build Garmin-only summary JSON exports in low, medium or full detail",
    )
    coach_exports.add_argument(
        "--date",
        default=None,
        help="Optional date in YYYY-MM-DD format. Defaults to latest available Garmin date.",
    )
    coach_exports.add_argument(
        "--days",
        type=int,
        default=1,
        help="How many days to summarize ending on --date. Defaults to 1.",
    )
    coach_exports.add_argument(
        "--level",
        choices=("low", "medium", "full", "all"),
        default="all",
        help="Export level to build. Defaults to all.",
    )

    activity_summaries = subparsers.add_parser(
        "activities-build-summaries",
        parents=[parent],
        help="Build cleaned summary JSON files for synced activities",
    )
    activity_summaries.add_argument(
        "--activity-id",
        default=None,
        help="Optional activity id to summarize. Defaults to all synced activities.",
    )
    activity_summaries.add_argument(
        "--date",
        default=None,
        help="Optional single calendar date in YYYY-MM-DD format.",
    )
    activity_summaries.add_argument(
        "--start-date",
        default=None,
        help="Optional start date in YYYY-MM-DD format.",
    )
    activity_summaries.add_argument(
        "--end-date",
        default=None,
        help="Optional end date in YYYY-MM-DD format.",
    )
    activity_summaries.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of activity summaries to build.",
    )

    purge_json = subparsers.add_parser(
        "purge-json",
        parents=[parent],
        help="Delete accumulated JSON artifacts under data/",
    )
    purge_json.add_argument(
        "--scope",
        choices=("raw", "normalized", "summaries", "all"),
        default="all",
        help="Which JSON roots to purge. Defaults to all.",
    )
    purge_json.add_argument(
        "--dry-run",
        action="store_true",
        help="Show how many JSON files would be deleted without deleting them.",
    )

    running_workout = subparsers.add_parser(
        "workout-create-running-intervals",
        parents=[parent],
        help="Create a Garmin running interval workout, optionally upload and schedule it",
    )
    running_workout.add_argument(
        "--name",
        default=None,
        help="Optional workout name. Defaults to a name derived from the workout spec.",
    )
    running_workout.add_argument(
        "--warmup-km",
        type=float,
        default=2.0,
        help="Warmup distance in km. Defaults to 2.0.",
    )
    running_workout.add_argument(
        "--repeats",
        type=int,
        required=True,
        help="Number of work intervals.",
    )
    running_workout.add_argument(
        "--interval-m",
        type=int,
        required=True,
        help="Distance of each interval in meters.",
    )
    running_workout.add_argument(
        "--pace-range",
        required=True,
        help="Target pace range in MM:SS-MM:SS per km, for example 5:15-5:25.",
    )
    running_workout.add_argument(
        "--recovery",
        default="2:00",
        help="Recovery between reps. Use MM:SS, HH:MM:SS or minutes as decimal. Defaults to 2:00.",
    )
    running_workout.add_argument(
        "--cooldown-km",
        default="1",
        help="Cooldown distance in km. You can pass a range like 1-2 to end manually with the lap button.",
    )
    running_workout.add_argument(
        "--description",
        default=None,
        help="Optional Garmin workout description.",
    )
    running_workout.add_argument(
        "--upload",
        action="store_true",
        help="Upload the workout to Garmin Connect after generating the JSON file.",
    )
    running_workout.add_argument(
        "--schedule-date",
        default=None,
        help="Optional Garmin calendar date in YYYY-MM-DD. Implies --upload.",
    )

    cycling_workout = subparsers.add_parser(
        "workout-create-cycling-intervals",
        parents=[parent],
        help="Create a Garmin cycling interval workout, optionally upload and schedule it",
    )
    cycling_workout.add_argument(
        "--name",
        default=None,
        help="Optional workout name. Defaults to a name derived from the workout spec.",
    )
    cycling_workout.add_argument(
        "--warmup",
        default="15:00",
        help="Warmup duration. Use MM:SS, HH:MM:SS or minutes as decimal. Defaults to 15:00.",
    )
    cycling_workout.add_argument(
        "--warmup-target",
        default=None,
        help="Optional free-text warmup target, for example RPE 3/10 or cadence 85-95 rpm.",
    )
    cycling_workout.add_argument(
        "--repeats",
        type=int,
        required=True,
        help="Number of work intervals.",
    )
    cycling_workout.add_argument(
        "--interval-duration",
        required=True,
        help="Duration of each work interval. Use MM:SS, HH:MM:SS or minutes as decimal.",
    )
    cycling_workout.add_argument(
        "--interval-target",
        default=None,
        help="Optional free-text work interval target, for example RPE 7/10 or 220-250W.",
    )
    cycling_workout.add_argument(
        "--recovery",
        default="2:00",
        help="Recovery between reps. Use MM:SS, HH:MM:SS or minutes as decimal. Defaults to 2:00.",
    )
    cycling_workout.add_argument(
        "--recovery-target",
        default=None,
        help="Optional free-text recovery target.",
    )
    cycling_workout.add_argument(
        "--keep-last-recovery",
        action="store_true",
        help="Keep the recovery step after the last work interval.",
    )
    cycling_workout.add_argument(
        "--steady-duration",
        default=None,
        help="Optional steady aerobic block after the repeats. Use MM:SS, HH:MM:SS or minutes as decimal.",
    )
    cycling_workout.add_argument(
        "--steady-target",
        default=None,
        help="Optional free-text target for the steady aerobic block.",
    )
    cycling_workout.add_argument(
        "--cooldown",
        default="10:00",
        help="Cooldown duration. Use MM:SS, HH:MM:SS or minutes as decimal. Defaults to 10:00.",
    )
    cycling_workout.add_argument(
        "--cooldown-target",
        default=None,
        help="Optional free-text cooldown target.",
    )
    cycling_workout.add_argument(
        "--target",
        default=None,
        help="Optional legacy free-text target for work intervals. Prefer --interval-target.",
    )
    cycling_workout.add_argument(
        "--description",
        default=None,
        help="Optional Garmin workout description.",
    )
    cycling_workout.add_argument(
        "--upload",
        action="store_true",
        help="Upload the workout to Garmin Connect after generating the JSON file.",
    )
    cycling_workout.add_argument(
        "--schedule-date",
        default=None,
        help="Optional Garmin calendar date in YYYY-MM-DD. Implies --upload.",
    )

    return parser


def main() -> int:
    """CLI entrypoint."""

    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "login-test":
            client, _, _ = _build_services(args.env_file)
            _print_json(client.login_test())
            return 0

        if args.command == "sync-daily":
            _, daily_sync, _ = _build_services(args.env_file)
            result: dict[str, Any] = {"sync": daily_sync.sync_date(args.date)}
            coach_service = _build_coach_service(args.env_file)
            if args.build_exports:
                result["exports"] = coach_service.build_exports(
                    args.date,
                    level=args.export_level,
                    window_days=1,
                )
            if args.build_activity_summaries:
                result["activity_summaries"] = coach_service.build_activity_summaries(
                    start_date=args.date,
                    end_date=args.date,
                )
            _print_json(result)
            return 0

        if args.command == "sync-last-30-days":
            _, _, activity_sync = _build_services(args.env_file)
            result = {
                "sync": activity_sync.sync_window(args.end_date, days=args.days)
            }
            coach_service = _build_coach_service(args.env_file)
            if args.build_exports:
                result["exports"] = coach_service.build_exports(
                    args.end_date,
                    level=args.export_level,
                    window_days=args.days,
                )
            if args.build_activity_summaries:
                start_date = (
                    parse_iso_date(args.end_date) - timedelta(days=args.days - 1)
                ).isoformat()
                result["activity_summaries"] = coach_service.build_activity_summaries(
                    start_date=start_date,
                    end_date=args.end_date,
                )
            _print_json(result)
            return 0

        coach_service = _build_coach_service(args.env_file)

        if args.command == "coach-build-context":
            _print_json(coach_service.build_context(args.date))
            return 0

        if args.command == "coach-build-exports":
            _print_json(
                coach_service.build_exports(
                    args.date,
                    level=args.level,
                    window_days=args.days,
                )
            )
            return 0

        if args.command == "activities-build-summaries":
            start_date = args.start_date
            end_date = args.end_date
            if args.date is not None:
                start_date = args.date
                end_date = args.date
            _print_json(
                coach_service.build_activity_summaries(
                    activity_id=args.activity_id,
                    limit=args.limit,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            return 0

        if args.command == "purge-json":
            cleanup_service = _build_cleanup_service(args.env_file)
            _print_json(
                cleanup_service.purge_json(
                    scope=args.scope,
                    dry_run=args.dry_run,
                )
            )
            return 0

        if args.command == "workout-create-running-intervals":
            workout_service, client = _build_running_workout_service(args.env_file)
            spec = workout_service.parse_spec(
                name=args.name,
                warmup_km=args.warmup_km,
                repeats=args.repeats,
                interval_m=args.interval_m,
                pace_range=args.pace_range,
                recovery=args.recovery,
                cooldown_km=args.cooldown_km,
                description=args.description,
            )
            result = workout_service.create_and_save(spec)
            if args.upload or args.schedule_date:
                upload_response = client.upload_workout(result["workout_payload"])
                garmin_result: dict[str, Any] = {
                    "upload_response": _summarize_workout_upload_response(
                        upload_response
                    ),
                }
                workout_id = upload_response.get("workoutId") or upload_response.get("id")
                if args.schedule_date is not None:
                    if workout_id is None:
                        raise ValueError(
                            "Garmin upload response did not include a workout id, so it cannot be scheduled."
                        )
                    garmin_result["schedule_response"] = _summarize_schedule_response(
                        client.schedule_workout(
                            workout_id,
                            args.schedule_date,
                        )
                    )
                result["garmin"] = garmin_result
            _print_json(result)
            return 0

        if args.command == "workout-create-cycling-intervals":
            workout_service, client = _build_cycling_workout_service(args.env_file)
            spec = workout_service.parse_spec(
                name=args.name,
                warmup=args.warmup,
                repeats=args.repeats,
                interval_duration=args.interval_duration,
                recovery=args.recovery,
                cooldown=args.cooldown,
                target=args.target,
                warmup_target=args.warmup_target,
                interval_target=args.interval_target,
                recovery_target=args.recovery_target,
                steady_duration=args.steady_duration,
                steady_target=args.steady_target,
                cooldown_target=args.cooldown_target,
                skip_last_recovery=not args.keep_last_recovery,
                description=args.description,
            )
            result = workout_service.create_and_save(spec)
            if args.upload or args.schedule_date:
                upload_response = client.upload_workout(result["workout_payload"])
                garmin_result: dict[str, Any] = {
                    "upload_response": _summarize_workout_upload_response(
                        upload_response
                    ),
                }
                workout_id = upload_response.get("workoutId") or upload_response.get("id")
                if args.schedule_date is not None:
                    if workout_id is None:
                        raise ValueError(
                            "Garmin upload response did not include a workout id, so it cannot be scheduled."
                        )
                    garmin_result["schedule_response"] = _summarize_schedule_response(
                        client.schedule_workout(
                            workout_id,
                            args.schedule_date,
                        )
                    )
                result["garmin"] = garmin_result
            _print_json(result)
            return 0

    except (GarminCoachError, ValueError) as exc:
        parser.exit(status=1, message=f"{exc}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
