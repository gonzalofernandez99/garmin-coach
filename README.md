# garmin-coach

English | [Español](README.es.md)

`garmin-coach` is a personal Python project built on top of `python-garminconnect` to:

- sync Garmin Connect data locally
- generate deterministic JSON artifacts
- build derived summaries and exports
- create and upload Garmin running workouts

## Scope

Current features:

- secure local auth with `.env` and Garmin token reuse
- daily sync and rolling-window sync
- per-activity summaries
- Garmin-derived low / medium / full exports
- running workout generation, upload, and optional scheduling

The project is local-first. It stores Garmin data on disk for personal analysis and downstream use.

## Requirements

- Python 3.12 or newer
- a Garmin Connect account
- run commands from the repository root

## Installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

## Configuration

1. Copy `.env.example` to `.env`
2. Set at least `GARMIN_EMAIL` and `GARMIN_PASSWORD`
3. Keep `.env`, `.secrets/`, `data/`, and local logs out of version control

```bash
cp .env.example .env
```

## Privacy

This project handles personal health and activity data.

- Do not commit `.env`, `.secrets/`, or `data/`
- Treat `data/raw/` and `data/summaries/` as private
- `full` exports may include raw Garmin payloads and should not be shared publicly
- CLI outputs are intentionally sanitized for account identity where possible, but your local JSON artifacts still contain sensitive data

## Main Commands

Validate Garmin authentication:

```bash
garmin-coach login-test
```

Sync one day:

```bash
garmin-coach sync-daily --date 2026-03-24
```

Sync one day and build exports:

```bash
garmin-coach sync-daily --date 2026-03-24 --build-exports
```

Sync a recent window and activity details:

```bash
garmin-coach sync-last-30-days --end-date 2026-03-24
```

Sync a recent window and build only the `medium` export:

```bash
garmin-coach sync-last-30-days --end-date 2026-03-24 --build-exports --export-level medium
```

Sync 30 days, build one `medium` export, and summarize each activity:

```bash
garmin-coach sync-last-30-days --end-date 2026-03-24 --days 30 --build-exports --export-level medium --build-activity-summaries
```

Sync up to a cutoff date and choose how many days back to fetch:

```bash
garmin-coach sync-last-30-days --end-date 2026-04-01 --days 7
```

That fetches an inclusive window from `2026-03-26` through `2026-04-01`.

Sync yesterday and today, while also building the daily summary and date-scoped activity summaries:

```bash
garmin-coach sync-last-30-days --end-date 2026-04-01 --days 2 --build-exports --export-level medium --build-activity-summaries
```

If you prefer to run each day separately:

```bash
garmin-coach sync-daily --date 2026-03-31 --build-exports --export-level medium --build-activity-summaries
garmin-coach sync-daily --date 2026-04-01 --build-exports --export-level medium --build-activity-summaries
```

Build the derived Garmin context:

```bash
garmin-coach coach-build-context --date 2026-03-24
```

Build exports:

```bash
garmin-coach coach-build-exports --date 2026-03-24
garmin-coach coach-build-exports --date 2026-03-24 --level medium
garmin-coach coach-build-exports --date 2026-03-24 --days 30 --level medium
```

Build summaries for all synced activities:

```bash
garmin-coach activities-build-summaries
```

Build activity summaries for a date range:

```bash
garmin-coach activities-build-summaries --start-date 2026-03-31 --end-date 2026-04-01
```

Build activity summaries for a single date:

```bash
garmin-coach activities-build-summaries --date 2026-04-01
```

Build the summary for a single activity:

```bash
garmin-coach activities-build-summaries --activity-id 21964227769
```

Create a running workout and save it locally as JSON:

```bash
garmin-coach workout-create-running-intervals \
  --name "Half marathon 5x1000m 5:15-5:25" \
  --warmup-km 2 \
  --repeats 5 \
  --interval-m 1000 \
  --pace-range 5:15-5:25 \
  --recovery 2:00 \
  --cooldown-km 1-2
```

Create the same workout and upload it to Garmin Connect:

```bash
garmin-coach workout-create-running-intervals \
  --name "Half marathon 5x1000m 5:15-5:25" \
  --warmup-km 2 \
  --repeats 5 \
  --interval-m 1000 \
  --pace-range 5:15-5:25 \
  --recovery 2:00 \
  --cooldown-km 1-2 \
  --upload
```

Upload it and schedule it on a Garmin calendar date:

```bash
garmin-coach workout-create-running-intervals \
  --name "Half marathon 5x1000m 5:15-5:25" \
  --warmup-km 2 \
  --repeats 5 \
  --interval-m 1000 \
  --pace-range 5:15-5:25 \
  --recovery 2:00 \
  --cooldown-km 1-2 \
  --upload \
  --schedule-date 2026-03-28
```

Preview JSON cleanup:

```bash
garmin-coach purge-json --dry-run
```

Delete generated JSON artifacts under `data/raw`, `data/normalized`, and `data/summaries`:

```bash
garmin-coach purge-json
```

## Generated Data

Raw Garmin payloads are stored under deterministic paths such as:

- `data/raw/account/profile/current.json`
- `data/raw/daily/user_summary/2026-03-24.json`
- `data/raw/daily/sleep/2026-03-24.json`
- `data/raw/activities/by_id/<activity_id>/details.json`

The project also writes derived artifacts such as:

- `data/normalized/coach/athlete_profile/current.json`
- `data/summaries/coach/packets/<date>.json`
- `data/summaries/coach/exports/low/<date>.json`
- `data/summaries/coach/exports/medium/<date>.json`
- `data/summaries/coach/exports/full/<date>.json`
- `data/summaries/coach/exports/<level>/latest.json`
- `data/summaries/activities/by_date/<activity_date>_<time>_<activity_name>_<activity_id>.json`
- `data/summaries/workouts/running/<timestamp>_<workout_name>.json`

Export levels:

- `low`: lightweight Garmin snapshot plus recent load
- `medium`: richer daily context, recent sessions, zone times, and discipline-specific metrics
- `full`: derived summary plus raw Garmin payloads for the date or date window

SQLite is used locally to track artifact hashes and sync reports so unchanged payloads are not rewritten unnecessarily.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Notes

- metric availability depends on the Garmin device, account, and endpoint support
- sync is designed to continue when an individual metric is unavailable
- some Garmin resources overlap depending on device support, especially `stress` and `body_battery`
