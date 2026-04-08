"""Tests for coach context, generic exports and activity summaries."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from garmin_coach.coach.service import CoachService
from garmin_coach.config import Settings
from garmin_coach.storage.raw_store import RawJsonStore


def _build_settings(root: Path) -> Settings:
    data_dir = root / "data"
    return Settings(
        project_root=root,
        env_file=root / ".env",
        email=None,
        password=None,
        tokenstore_path=root / ".secrets" / "garmin_tokens",
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        normalized_dir=data_dir / "normalized",
        summaries_dir=data_dir / "summaries",
        logs_dir=data_dir / "logs",
        sqlite_path=data_dir / "state" / "garmin_coach.db",
        region="global",
        log_level="INFO",
        retries=1,
        retry_backoff_seconds=0.0,
    )


def _seed_raw_data(store: RawJsonStore) -> None:
    store.save_json(
        "account/user_settings/current.json",
        {
            "userData": {
                "birthDate": "1999-01-13",
                "gender": "MALE",
                "height": 179.0,
                "weight": 82000.0,
                "vo2MaxRunning": 47.0,
                "lactateThresholdHeartRate": 30,
                "ftpAutoDetected": True,
                "thresholdHeartRateAutoDetected": False,
            }
        },
    )
    store.save_json(
        "account/profile_settings/current.json",
        {
            "timeZone": "America/Argentina/Buenos_Aires",
            "preferredLocale": "es",
            "measurementSystem": "metric",
        },
    )
    store.save_json(
        "device/primary_training_device/current.json",
        {
            "PrimaryTrainingDevices": {
                "deviceWeights": [{"displayName": "Instinct 2"}]
            },
            "RegisteredDevices": [
                {
                    "primary": True,
                    "deviceTypeSimpleName": "Garmin Instinct 2",
                    "currentFirmwareVersion": "17.08",
                    "hrvStatusCapable": True,
                    "racePredictionsRunCapable": True,
                    "primaryTrainingCapable": True,
                }
            ],
        },
    )
    store.save_json(
        "training/race_predictions/latest.json",
        {
            "calendarDate": "2026-03-24",
            "time5K": 1487,
            "time10K": 3192,
            "timeHalfMarathon": 7291,
            "timeMarathon": 16307,
        },
    )
    store.save_json(
        "daily/user_summary/2026-03-24.json",
        {
            "calendarDate": "2026-03-24",
            "totalSteps": 1820,
            "totalDistanceMeters": 57048,
            "activeKilocalories": 751,
            "restingHeartRate": 44,
            "bodyBatteryAtWakeTime": 94,
            "averageStressLevel": 17,
            "sleepingSeconds": 27720,
            "avgWakingRespirationValue": 13.0,
        },
    )
    store.save_json(
        "daily/sleep/2026-03-24.json",
        {
            "dailySleepDTO": {
                "calendarDate": "2026-03-24",
                "sleepTimeSeconds": 26400,
                "deepSleepSeconds": 7860,
                "lightSleepSeconds": 12540,
                "remSleepSeconds": 6000,
                "awakeSleepSeconds": 1320,
                "averageRespirationValue": 14.0,
                "avgSleepStress": 10.0,
                "sleepScoreInsight": "POSITIVE_LATE_BED_TIME",
                "sleepScoreFeedback": "POSITIVE_LONG_AND_RECOVERING",
                "sleepScores": {
                    "overall": {"value": 89, "qualifierKey": "GOOD"}
                },
            }
        },
    )
    store.save_json(
        "daily/hrv/2026-03-24.json",
        {
            "hrvSummary": {
                "calendarDate": "2026-03-24",
                "status": "BALANCED",
                "feedbackPhrase": "HRV_BALANCED_2",
                "lastNightAvg": 81,
                "weeklyAvg": 76,
                "baseline": {
                    "balancedLow": 69,
                    "balancedUpper": 82,
                },
            }
        },
    )
    store.save_json(
        "daily/training_readiness/2026-03-24.json",
        [
            {
                "calendarDate": "2026-03-24",
                "score": 62,
                "level": "MODERATE",
                "sleepScore": 89,
                "hrvWeeklyAverage": 76,
                "recoveryTime": 2008,
                "feedbackShort": "BOOSTED_BY_GOOD_SLEEP",
                "feedbackLong": "MOD_RT_MOD_SS_GOOD",
                "sleepScoreFactorFeedback": "GOOD",
                "hrvFactorFeedback": "GOOD",
                "stressHistoryFactorFeedback": "GOOD",
                "recoveryTimeFactorFeedback": "MODERATE",
            }
        ],
    )
    store.save_json(
        "daily/training_status/2026-03-24.json",
        {
            "mostRecentTrainingStatus": {
                "latestTrainingStatusData": {
                    "3477509168": {
                        "calendarDate": "2026-03-24",
                        "sport": "RUNNING",
                        "trainingStatusFeedbackPhrase": "MAINTAINING_2",
                        "fitnessTrend": 2,
                        "acuteTrainingLoadDTO": {
                            "acwrStatus": "OPTIMAL",
                            "acwrPercent": 47,
                            "dailyTrainingLoadAcute": 772,
                            "dailyTrainingLoadChronic": 651,
                        },
                    }
                }
            },
            "mostRecentTrainingLoadBalance": {
                "metricsTrainingLoadBalanceDTOMap": {
                    "3477509168": {
                        "trainingBalanceFeedbackPhrase": "AEROBIC_HIGH_SHORTAGE",
                        "monthlyLoadAerobicLow": 1786.6,
                        "monthlyLoadAerobicHigh": 291.2,
                        "monthlyLoadAnaerobic": 551.5,
                    }
                }
            },
            "mostRecentVO2Max": {
                "generic": {
                    "vo2MaxValue": 47.0,
                }
            },
        },
    )
    store.save_json(
        "daily/hydration/2026-03-24.json",
        {
            "calendarDate": "2026-03-24",
            "valueInML": 0.0,
            "goalInML": 4169.0,
            "sweatLossInML": 1330.0,
            "activityIntakeInML": 0.0,
        },
    )
    store.save_json(
        "daily/body_composition/2026-03-24.json",
        {
            "dateWeightList": [],
            "totalAverage": {
                "weight": None,
            },
        },
    )
    store.save_json(
        "daily/activities/2026-03-24.json",
        [
            {
                "activityId": 101,
                "activityName": "Lanus Ciclismo en ruta",
                "activityTrainingLoad": 74.4,
                "activityType": {"typeKey": "road_biking"},
                "averageHR": 123.0,
                "maxHR": 174.0,
                "averageSpeed": 6.93,
                "elevationGain": 420.0,
                "elevationLoss": 418.0,
                "avgRespirationRate": 24.6,
                "waterEstimated": 1200.0,
                "hrTimeInZone_1": 1200.0,
                "hrTimeInZone_2": 2400.0,
                "hrTimeInZone_3": 1800.0,
                "hrTimeInZone_4": 600.0,
                "hrTimeInZone_5": 0.0,
                "distance": 55637.9,
                "duration": 8028.7,
                "movingDuration": 7996.1,
                "startTimeLocal": "2026-03-24 10:46:17",
                "aerobicTrainingEffect": 2.8,
                "anaerobicTrainingEffect": 0.4,
                "trainingEffectLabel": "AEROBIC_BASE",
            }
        ],
    )
    store.save_json(
        "daily/activities/2026-03-22.json",
        [
            {
                "activityId": 202,
                "activityName": "Rodaje",
                "activityTrainingLoad": 52.0,
                "activityType": {"typeKey": "running"},
                "averageHR": 145.0,
                "maxHR": 162.0,
                "averageSpeed": 3.8,
                "averageRunningCadenceInStepsPerMinute": 162.0,
                "avgStrideLength": 102.0,
                "avgPower": 245.0,
                "normPower": 252.0,
                "avgGradeAdjustedSpeed": 3.7,
                "steps": 10850,
                "hrTimeInZone_1": 300.0,
                "hrTimeInZone_2": 1200.0,
                "hrTimeInZone_3": 1500.0,
                "hrTimeInZone_4": 600.0,
                "hrTimeInZone_5": 0.0,
                "distance": 12000.0,
                "duration": 3600.0,
                "movingDuration": 3560.0,
                "startTimeLocal": "2026-03-22 08:15:00",
                "aerobicTrainingEffect": 3.1,
                "anaerobicTrainingEffect": 0.2,
                "trainingEffectLabel": "TEMPO",
            }
        ],
    )
    store.save_json(
        "activities/by_id/101/list_entry.json",
        {
            "activityId": 101,
            "activityName": "Lanus Ciclismo en ruta",
            "activityTrainingLoad": 74.4,
            "activityType": {"typeKey": "road_biking"},
            "averageHR": 123.0,
            "maxHR": 174.0,
            "averageSpeed": 6.93,
            "distance": 55637.9,
            "duration": 8028.7,
            "movingDuration": 7996.1,
            "startTimeLocal": "2026-03-24 10:46:17",
            "elevationGain": 420.0,
            "elevationLoss": 418.0,
            "trainingEffectLabel": "AEROBIC_BASE",
            "waterEstimated": 1200.0,
        },
    )
    store.save_json(
        "activities/by_id/101/split_summaries.json",
        {"activityId": 101, "splitSummaries": []},
    )
    store.save_json(
        "activities/by_id/101/splits.json",
        {
            "activityId": 101,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 5000.0,
                    "duration": 900.0,
                    "averageHR": 120.0,
                    "maxHR": 132.0,
                    "averageSpeed": 5.5555555556,
                    "elevationGain": 18.0,
                    "elevationLoss": 8.0,
                },
                {
                    "lapIndex": 2,
                    "distance": 5000.0,
                    "duration": 870.0,
                    "averageHR": 128.0,
                    "maxHR": 140.0,
                    "averageSpeed": 5.7471264368,
                    "elevationGain": 22.0,
                    "elevationLoss": 10.0,
                },
            ],
        },
    )
    store.save_json(
        "activities/by_id/101/details.json",
        {"activityDetailMetrics": [{"metrics": [0.0, 110.0, 0.0, 1771844784000.0]}]},
    )
    store.save_json(
        "activities/by_id/202/list_entry.json",
        {
            "activityId": 202,
            "activityName": "Rodaje",
            "activityTrainingLoad": 52.0,
            "activityType": {"typeKey": "running"},
            "averageHR": 145.0,
            "maxHR": 162.0,
            "averageRunningCadenceInStepsPerMinute": 162.0,
            "avgStrideLength": 102.0,
            "avgPower": 245.0,
            "normPower": 252.0,
            "averageSpeed": 3.8,
            "distance": 12000.0,
            "duration": 3600.0,
            "movingDuration": 3560.0,
            "startTimeLocal": "2026-03-22 08:15:00",
            "elevationGain": 85.0,
            "elevationLoss": 82.0,
            "calories": 820.0,
            "trainingEffectLabel": "TEMPO",
        },
    )
    store.save_json(
        "activities/by_id/202/split_summaries.json",
        {
            "activityId": 202,
            "splitSummaries": [
                {
                    "splitType": "RWD_RUN",
                    "distance": 12000.0,
                    "duration": 3600.0,
                    "movingDuration": 3560.0,
                    "averageHR": 145.0,
                    "maxHR": 162.0,
                    "averageSpeed": 3.8,
                    "averagePower": 245.0,
                    "normalizedPower": 252.0,
                    "averageRunCadence": 162.0,
                    "elevationGain": 85.0,
                    "elevationLoss": 82.0,
                }
            ],
        },
    )
    store.save_json(
        "activities/by_id/202/details.json",
        {"activityDetailMetrics": [{"metrics": [0.0, 130.0, 0.0, 1771844784000.0]}]},
    )
    store.save_json(
        "activities/by_id/202/splits.json",
        {
            "activityId": 202,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 1000.0,
                    "duration": 300.0,
                    "averageHR": 140.0,
                    "maxHR": 148.0,
                    "averageSpeed": 3.3333333333,
                    "averageRunCadence": 164.0,
                    "averagePower": 250.0,
                    "normalizedPower": 255.0,
                },
                {
                    "lapIndex": 2,
                    "distance": 1000.0,
                    "duration": 295.0,
                    "averageHR": 145.0,
                    "maxHR": 154.0,
                    "averageSpeed": 3.3898305085,
                    "averageRunCadence": 166.0,
                    "averagePower": 255.0,
                    "normalizedPower": 260.0,
                },
            ],
        },
    )
    store.save_json(
        "activities/by_id/303/list_entry.json",
        {
            "activityId": 303,
            "activityName": "Natacion tecnica",
            "activityTrainingLoad": 38.0,
            "activityType": {"typeKey": "lap_swimming"},
            "averageHR": 112.0,
            "maxHR": 136.0,
            "averageSwimCadenceInStrokesPerMinute": 25.0,
            "distance": 400.0,
            "duration": 520.0,
            "movingDuration": 500.0,
            "startTimeLocal": "2026-03-21 07:00:00",
            "poolLength": 2500.0,
            "activeLengths": 16,
            "strokes": 180,
            "averageSwolf": 39.0,
            "calories": 210.0,
            "trainingEffectLabel": "RECOVERY",
        },
    )
    store.save_json(
        "activities/by_id/303/split_summaries.json",
        {"activityId": 303, "splitSummaries": []},
    )
    store.save_json(
        "activities/by_id/303/splits.json",
        {
            "activityId": 303,
            "lapDTOs": [
                {
                    "lapIndex": 1,
                    "distance": 200.0,
                    "duration": 220.0,
                    "averageHR": 110.0,
                    "maxHR": 120.0,
                    "averageSpeed": 0.9090909091,
                    "averageSWOLF": 38.0,
                    "averageSwimCadence": 25.0,
                    "averageStrokes": 11.5,
                    "lengthDTOs": [{}, {}, {}, {}, {}, {}, {}, {}],
                },
                {
                    "lapIndex": 2,
                    "distance": 0.0,
                    "duration": 30.0,
                    "averageHR": 108.0,
                    "maxHR": 111.0,
                    "averageSpeed": 0.0,
                    "averageSWOLF": 0.0,
                    "averageSwimCadence": 0.0,
                    "lengthDTOs": [],
                },
            ],
        },
    )
    store.save_json(
        "activities/by_id/303/details.json",
        {"activityDetailMetrics": [{"metrics": [0.0, 100.0, 0.0, 1771844784000.0]}]},
    )


class CoachServiceTest(unittest.TestCase):
    def test_build_context_redacts_pii_and_aggregates_recent_training(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            context = service.build_context("2026-03-24")

            athlete_profile = context["athlete_profile"]
            coach_packet = context["coach_packet"]

            self.assertEqual(
                athlete_profile["athlete"]["timezone"],
                "America/Argentina/Buenos_Aires",
            )
            self.assertEqual(athlete_profile["athlete"]["weight_kg"], 82.0)
            self.assertNotIn("fullName", athlete_profile["athlete"])
            self.assertTrue(athlete_profile["data_quality_flags"])
            self.assertEqual(
                coach_packet["recent_training"]["rolling_7d"]["session_count"],
                2,
            )
            self.assertEqual(
                coach_packet["recent_training"]["rolling_28d"]["by_discipline"]["bike"]["session_count"],
                1,
            )

    def test_build_context_dedupes_duplicate_activities(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)
            store.save_json(
                "daily/activities/2026-03-23.json",
                [
                    {
                        "activityId": 101,
                        "activityName": "Lanus Ciclismo en ruta",
                        "activityTrainingLoad": 74.4,
                        "activityType": {"typeKey": "road_biking"},
                        "averageHR": 123.0,
                        "maxHR": 174.0,
                        "averageSpeed": 6.93,
                        "distance": 55637.9,
                        "duration": 8028.7,
                        "movingDuration": 7996.1,
                        "startTimeLocal": "2026-03-24 10:46:17",
                        "aerobicTrainingEffect": 2.8,
                        "anaerobicTrainingEffect": 0.4,
                        "trainingEffectLabel": "AEROBIC_BASE",
                    }
                ],
            )

            service = CoachService(settings)
            context = service.build_context("2026-03-24")
            coach_packet = context["coach_packet"]

            self.assertEqual(
                coach_packet["recent_training"]["rolling_7d"]["session_count"],
                2,
            )

    def test_build_exports_all_levels(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            result = service.build_exports("2026-03-24", level="all")

            self.assertEqual(result["requested_level"], "all")
            self.assertEqual(set(result["exports"]), {"low", "medium", "full"})

            for level in ("low", "medium", "full"):
                dated_path = (
                    settings.summaries_dir / "coach" / "exports" / level / "2026-03-24.json"
                )
                latest_path = (
                    settings.summaries_dir / "coach" / "exports" / level / "latest.json"
                )
                self.assertTrue(dated_path.exists())
                self.assertTrue(latest_path.exists())

    def test_export_levels_have_expected_granularity(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            service.build_exports("2026-03-24", level="all")

            base_path = settings.summaries_dir / "coach" / "exports"
            low_payload = json.loads(
                (base_path / "low" / "2026-03-24.json").read_text(encoding="utf-8")
            )
            medium_payload = json.loads(
                (base_path / "medium" / "2026-03-24.json").read_text(encoding="utf-8")
            )
            full_payload = json.loads(
                (base_path / "full" / "2026-03-24.json").read_text(encoding="utf-8")
            )

            self.assertEqual(low_payload["export_level"], "low")
            self.assertIn("summary", low_payload)
            self.assertIn("recent_training", low_payload)
            self.assertNotIn("raw_data", low_payload)

            self.assertEqual(medium_payload["export_level"], "medium")
            self.assertIn("daily_context", medium_payload)
            self.assertIn("recent_training", medium_payload)
            self.assertNotIn("raw_data", medium_payload)

            self.assertEqual(full_payload["export_level"], "full")
            self.assertIn("summary", full_payload)
            self.assertIn("raw_data", full_payload)
            self.assertIn("activities", full_payload["raw_data"])
            self.assertIn("training_status", full_payload["raw_data"])

            running_session = next(
                item
                for item in medium_payload["recent_training"]["last_sessions"]
                if item["discipline"] == "run"
            )
            self.assertEqual(
                running_session["heart_rate_zone_times_minutes"]["z3"],
                25.0,
            )
            self.assertEqual(
                running_session["sport_specific"]["cadence_spm"],
                162.0,
            )

    def test_medium_export_can_summarize_a_window(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            result = service.build_exports(
                "2026-03-24",
                level="medium",
                window_days=3,
            )

            self.assertEqual(result["window_days"], 3)

            payload = json.loads(
                (
                    settings.summaries_dir / "coach" / "exports" / "medium" / "2026-03-24.json"
                ).read_text(encoding="utf-8")
            )

            self.assertEqual(
                payload["window"],
                {
                    "start_date": "2026-03-22",
                    "end_date": "2026-03-24",
                    "days_requested": 3,
                    "days_with_any_data": 2,
                },
            )
            self.assertEqual(len(payload["daily_context_by_date"]), 3)
            self.assertEqual(
                payload["recent_training"]["rolling_3d"]["session_count"],
                2,
            )

    def test_build_activity_summaries_for_all_available_activities(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            result = service.build_activity_summaries()

            self.assertEqual(result["activity_count"], 3)
            bike_path = (
                settings.summaries_dir
                / "activities"
                / "by_date"
                / "2026-03-24_10-46-17_lanus-ciclismo-en-ruta_101.json"
            )
            run_path = (
                settings.summaries_dir
                / "activities"
                / "by_date"
                / "2026-03-22_08-15-00_rodaje_202.json"
            )
            self.assertTrue(bike_path.exists())
            self.assertTrue(run_path.exists())

            run_payload = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(run_payload["discipline"], "run")
            self.assertEqual(run_payload["activity_date"], "2026-03-22")
            self.assertEqual(run_payload["activity_start_local"], "2026-03-22T08:15:00")
            self.assertEqual(run_payload["overview"]["distance_km"], 12.0)
            self.assertEqual(len(run_payload["split_summaries"]), 1)
            self.assertEqual(len(run_payload["segment_breakdown"]), 2)
            self.assertEqual(run_payload["segment_breakdown"][0]["label"], "km 1")
            self.assertEqual(
                run_payload["segment_breakdown"][0]["pace_per_km_display"],
                "5:00/km",
            )
            self.assertEqual(
                run_payload["segment_breakdown"][0]["average_hr"],
                140.0,
            )

    def test_build_activity_summaries_for_single_activity(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            result = service.build_activity_summaries(activity_id="101")

            self.assertEqual(result["activity_count"], 1)
            payload = json.loads(
                (
                    settings.summaries_dir
                    / "activities"
                    / "by_date"
                    / "2026-03-24_10-46-17_lanus-ciclismo-en-ruta_101.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["discipline"], "bike")
            self.assertEqual(payload["activity_date"], "2026-03-24")
            self.assertEqual(payload["activity_start_local"], "2026-03-24T10:46:17")
            self.assertEqual(payload["overview"]["training_effect_label"], "AEROBIC_BASE")
            self.assertIn("list_entry.json", payload["available_raw_files"])
            self.assertEqual(payload["segment_breakdown"][0]["label"], "lap 1")
            self.assertEqual(
                payload["segment_breakdown"][0]["average_speed_kmh"],
                20.0,
            )
            self.assertEqual(payload["segment_breakdown"][0]["average_hr"], 120.0)

    def test_build_activity_summaries_filtered_by_date_range(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            result = service.build_activity_summaries(
                start_date="2026-03-22",
                end_date="2026-03-24",
            )

            self.assertEqual(result["activity_count"], 2)
            self.assertEqual(result["start_date"], "2026-03-22")
            self.assertEqual(result["end_date"], "2026-03-24")
            saved_paths = {Path(item["path"]).name for item in result["items"]}
            self.assertEqual(
                saved_paths,
                {
                    "2026-03-22_08-15-00_rodaje_202.json",
                    "2026-03-24_10-46-17_lanus-ciclismo-en-ruta_101.json",
                },
            )

    def test_build_activity_summary_includes_swim_laps_and_rest_segments(self) -> None:
        with TemporaryDirectory() as tmpdir:
            settings = _build_settings(Path(tmpdir))
            settings.ensure_runtime_dirs()
            store = RawJsonStore(settings.raw_dir)
            _seed_raw_data(store)

            service = CoachService(settings)
            result = service.build_activity_summaries(activity_id="303")

            self.assertEqual(result["activity_count"], 1)
            payload = json.loads(
                (
                    settings.summaries_dir
                    / "activities"
                    / "by_date"
                    / "2026-03-21_07-00-00_natacion-tecnica_303.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["discipline"], "swim")
            self.assertTrue(payload["data_quality"]["has_segment_breakdown"])
            self.assertEqual(payload["segment_breakdown"][0]["label"], "lap 1")
            self.assertEqual(
                payload["segment_breakdown"][0]["pace_per_100m_display"],
                "1:50/100m",
            )
            self.assertEqual(payload["segment_breakdown"][0]["length_count"], 8)
            self.assertTrue(payload["segment_breakdown"][1]["is_rest"])


if __name__ == "__main__":
    unittest.main()
