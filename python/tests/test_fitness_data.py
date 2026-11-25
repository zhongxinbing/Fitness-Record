import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fitness_data import FitnessStore, FitnessStoreError


class FitnessStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "records.json"
        self.store = FitnessStore(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_persists_workout_and_calculates_monthly_training_volume(self):
        self.store.add_workout(
            "2026-11-18",
            "上肢训练",
            ["胸", "背"],
            [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
        )

        reloaded = FitnessStore(self.path)
        self.assertEqual(reloaded.monthly_summary("2026-11")["sessions"], 1)
        self.assertEqual(reloaded.monthly_summary("2026-11")["body_parts"]["胸"], 1)
        self.assertEqual(reloaded.training_volume_trend(), [("2026-11-18", 960.0)])

    def test_rejects_invalid_entries_without_saving_them(self):
        with self.assertRaises(ValueError):
            self.store.add_workout(
                "2026-11-18",
                "训练",
                ["腿"],
                [{"name": "深蹲", "sets": 0, "reps": 8, "weight": 30}],
            )
        with self.assertRaises(ValueError):
            self.store.add_body_weight("2026-11-18", -1)
        self.assertFalse(self.path.exists())

    def test_body_weight_trend_is_sorted_by_date(self):
        self.store.add_body_weight("2026-11-18", 70)
        self.store.add_body_weight("2026-11-01", 71)
        self.assertEqual(
            self.store.body_weight_trend(),
            [("2026-11-01", 71.0), ("2026-11-18", 70.0)],
        )

    def test_failed_write_keeps_memory_and_disk_unchanged(self):
        self.store.add_workout(
            "2026-11-18",
            "上肢训练",
            ["胸"],
            [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
        )
        previous_file = self.path.read_bytes()

        with patch("fitness_data.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(FitnessStoreError):
                self.store.add_body_weight("2026-11-18", 70)

        self.assertEqual(self.store.data["body_weights"], [])
        self.assertEqual(self.path.read_bytes(), previous_file)

    def test_rejects_malformed_persisted_records_without_overwriting_file(self):
        original = (
            '{"version": 1, "plans": [], "workouts": [{"id": "bad", '
            '"date": "not-a-date", "title": "训练", "body_parts": ["胸"], '
            '"exercises": [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}]}], '
            '"body_weights": []}'
        )
        self.path.write_text(original, encoding="utf-8")

        with self.assertRaises(FitnessStoreError):
            FitnessStore(self.path)

        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_failed_delete_keeps_record_available(self):
        workout = self.store.add_workout(
            "2026-11-18",
            "上肢训练",
            ["胸"],
            [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
        )

        with patch("fitness_data.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(FitnessStoreError):
                self.store.delete("workouts", workout["id"])

        self.assertEqual(len(self.store.recent_workouts()), 1)
        self.assertEqual(FitnessStore(self.path).recent_workouts()[0]["id"], workout["id"])

    def test_old_exercises_get_default_rest_and_empty_alternatives(self):
        plan = self.store.add_plan(
            "力量训练",
            ["胸"],
            [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
        )

        self.assertEqual(plan["exercises"][0]["rest_seconds"], 60)
        self.assertEqual(plan["exercises"][0]["alternatives"], [])

    def test_loads_legacy_exercise_without_rest_or_alternatives(self):
        self.path.write_text(
            '{"version": 1, "plans": [{"id": "plan-1", "title": "力量训练", '
            '"body_parts": ["胸"], "exercises": [{"name": "卧推", "sets": 3, '
            '"reps": 8, "weight": 40}]}], "workouts": [], "body_weights": []}',
            encoding="utf-8",
        )

        loaded = FitnessStore(self.path)

        self.assertEqual(loaded.data["plans"][0]["exercises"][0]["rest_seconds"], 60)
        self.assertEqual(loaded.data["plans"][0]["exercises"][0]["alternatives"], [])

    def test_loads_legacy_workout_without_time_as_unknown(self):
        self.path.write_text(
            '{"version": 1, "plans": [], "workouts": [{"id": "workout-1", '
            '"date": "2026-11-18", "title": "训练", "body_parts": ["胸"], '
            '"exercises": [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}], '
            '"notes": ""}], "body_weights": []}',
            encoding="utf-8",
        )

        loaded = FitnessStore(self.path)

        self.assertEqual(loaded.recent_workouts()[0]["training_time"], "")

    def test_recent_workouts_are_sorted_by_date_and_training_time(self):
        exercise = [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}]
        self.store.add_workout(
            "2026-11-17",
            "前一天",
            ["胸"],
            exercise,
            training_time="23:59",
        )
        self.store.add_workout(
            "2026-11-18",
            "早训",
            ["胸"],
            exercise,
            training_time="07:30",
        )
        self.store.add_workout(
            "2026-11-18",
            "晚训",
            ["胸"],
            exercise,
            training_time="18:45",
        )

        self.assertEqual(
            [item["title"] for item in self.store.recent_workouts()],
            ["晚训", "早训", "前一天"],
        )

    def test_rejects_invalid_training_time(self):
        with self.assertRaisesRegex(ValueError, "HH:MM"):
            self.store.add_workout(
                "2026-11-18",
                "训练",
                ["胸"],
                [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
                training_time="25:61",
            )

    def test_replaces_plan_exercise_and_validates_alternatives(self):
        plan = self.store.add_plan(
            "力量训练",
            ["胸"],
            [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
        )
        self.store.replace_exercises(
            "plans",
            plan["id"],
            [{
                "name": "哑铃卧推",
                "sets": 4,
                "reps": 10,
                "weight": 20,
                "rest_seconds": 90,
                "alternatives": ["杠铃卧推", "器械推胸"],
            }],
        )

        updated = FitnessStore(self.path).data["plans"][0]["exercises"][0]
        self.assertEqual(updated["sets"], 4)
        self.assertEqual(updated["weight"], 20.0)
        self.assertEqual(updated["rest_seconds"], 90)
        self.assertEqual(updated["alternatives"], ["杠铃卧推", "器械推胸"])

    def test_updates_template_details_and_persists_original_id(self):
        plan = self.store.add_plan(
            "推胸日",
            ["胸"],
            [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
        )

        updated = self.store.update_plan(
            plan["id"],
            "上肢力量",
            ["背", "肩"],
            [{
                "name": "坐姿划船",
                "sets": 4,
                "reps": 10,
                "weight": 35,
                "rest_seconds": 75,
            }],
        )
        reloaded = FitnessStore(self.path)

        self.assertEqual(updated["id"], plan["id"])
        self.assertEqual(updated["title"], "上肢力量")
        self.assertEqual(updated["body_parts"], ["背", "肩"])
        self.assertEqual(updated["exercises"][0]["name"], "坐姿划船")
        self.assertEqual(reloaded.data["plans"], [updated])

    def test_rejects_empty_template_update_without_changing_original(self):
        plan = self.store.add_plan(
            "推胸日",
            ["胸"],
            [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
        )
        with self.assertRaisesRegex(ValueError, "训练动作"):
            self.store.update_plan(plan["id"], "空计划", ["胸"], [])

        self.assertEqual(self.store.data["plans"], [plan])

    def test_rejects_rest_period_longer_than_timer_limit(self):
        with self.assertRaisesRegex(ValueError, "60 分钟"):
            self.store.add_plan(
                "力量训练",
                ["胸"],
                [{
                    "name": "卧推",
                    "sets": 3,
                    "reps": 8,
                    "weight": 40,
                    "rest_seconds": 3601,
                }],
            )

    def test_version_one_data_migrates_in_memory_without_losing_records(self):
        self.path.write_text(
            '{"version": 1, "plans": [], "workouts": [{"id": "workout-1", '
            '"date": "2026-11-18", "title": "训练", "body_parts": ["胸"], '
            '"exercises": [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}]}], '
            '"body_weights": []}',
            encoding="utf-8",
        )

        loaded = FitnessStore(self.path)

        self.assertEqual(loaded.data["version"], 2)
        self.assertEqual(loaded.data["rest_days"], [])
        self.assertEqual(len(loaded.data["workouts"]), 1)

    def test_daily_exercises_append_and_remove_persistently(self):
        first = {"name": "卧推", "sets": 4, "reps": 8, "weight": 60}
        second = {"name": "飞鸟", "sets": 3, "reps": 12, "weight": 15}
        workout = self.store.add_daily_exercise("2026-11-19", "胸", first)
        self.store.add_daily_exercise("2026-11-19", "胸", second)

        self.assertEqual(len(workout["exercises"]), 1)
        self.assertEqual(len(self.store.data["workouts"][0]["exercises"]), 2)
        self.store.remove_workout_exercise(workout["id"], 0)
        self.assertEqual(
            [item["name"] for item in FitnessStore(self.path).data["workouts"][0]["exercises"]],
            ["飞鸟"],
        )

    def test_removed_exercise_and_last_workout_can_be_restored(self):
        first = {"name": "卧推", "sets": 4, "reps": 8, "weight": 60}
        second = {"name": "飞鸟", "sets": 3, "reps": 12, "weight": 15}
        workout = self.store.add_daily_exercises(
            "2026-11-19",
            ["胸"],
            [first, second],
        )

        original = self.store.remove_workout_exercise(workout["id"], 0)
        self.store.restore_removed_workout_exercise(original, 0)
        restored = FitnessStore(self.path).data["workouts"][0]
        self.assertEqual(
            [item["name"] for item in restored["exercises"]],
            ["卧推", "飞鸟"],
        )
        self.assertEqual(restored["exercises"][0]["set_log"], original["exercises"][0]["set_log"])

        single_action_workout = self.store.add_daily_exercise(
            "2026-11-20",
            "腿",
            {"name": "深蹲", "sets": 3, "reps": 8, "weight": 80},
        )
        last_exercise_snapshot = self.store.remove_workout_exercise(
            single_action_workout["id"],
            0,
        )
        self.assertNotIn(
            single_action_workout["id"],
            [item["id"] for item in self.store.data["workouts"]],
        )
        self.store.restore_removed_workout_exercise(last_exercise_snapshot, 0)
        restored_workout = next(
            item
            for item in FitnessStore(self.path).data["workouts"]
            if item["id"] == single_action_workout["id"]
        )
        self.assertEqual(restored_workout["exercises"][0]["name"], "深蹲")

    def test_deleted_template_can_be_restored_with_original_id(self):
        template = self.store.add_plan(
            "推胸日",
            ["胸"],
            [{"name": "卧推", "sets": 4, "reps": 8, "weight": 60}],
        )

        self.store.delete("plans", template["id"])
        self.store.restore_plan(template)

        restored = FitnessStore(self.path).data["plans"]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["id"], template["id"])
        self.assertEqual(restored[0]["title"], "推胸日")

    def test_active_workout_duration_and_details_are_persisted(self):
        with patch("fitness_data.time.time", return_value=1000):
            workout = self.store.add_daily_exercise(
                "2026-11-19",
                "胸",
                {"name": "卧推", "sets": 3, "reps": 8, "weight": 60},
            )
        self.assertEqual(workout["started_at"], 1000)

        self.store.update_workout_details(workout["id"], "周一推训练", "状态不错")
        with patch("fitness_data.time.time", return_value=1465):
            finished = self.store.finish_workout("2026-11-19")

        self.assertIsNotNone(finished)
        self.assertEqual(finished["duration_seconds"], 465)
        persisted = FitnessStore(self.path).data["workouts"][0]
        self.assertEqual(persisted["title"], "周一推训练")
        self.assertEqual(persisted["notes"], "状态不错")
        self.assertEqual(persisted["duration_seconds"], 465)

    def test_editing_exercise_preserves_logged_sets_and_initializes_added_sets(self):
        workout = self.store.add_daily_exercise(
            "2026-11-19",
            "胸",
            {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
        )
        self.store.update_workout_set(
            workout["id"],
            0,
            0,
            weight=70,
            completed=True,
        )

        self.store.replace_workout_exercise(
            workout["id"],
            0,
            {"name": "器械卧推", "sets": 3, "reps": 10, "weight": 50},
        )

        exercise = FitnessStore(self.path).data["workouts"][0]["exercises"][0]
        self.assertEqual(exercise["weight"], 50.0)
        self.assertEqual(exercise["reps"], 10)
        self.assertEqual(
            exercise["set_log"],
            [
                {"weight": 70.0, "reps": 8, "completed": True},
                {"weight": 60.0, "reps": 8, "completed": False},
                {"weight": 50.0, "reps": 10, "completed": False},
            ],
        )

    def test_historical_exercises_are_grouped_as_completed_workout(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.store.set_rest_day(yesterday, True)

        self.store.add_historical_exercise(
            yesterday,
            "胸",
            {"name": "卧推", "sets": 3, "reps": 8, "weight": 60},
        )
        self.store.add_historical_exercise(
            yesterday,
            "背",
            {"name": "划船", "sets": 3, "reps": 10, "weight": 40},
        )

        workout = self.store.data["workouts"][0]
        self.assertEqual(len(self.store.data["workouts"]), 1)
        self.assertEqual(workout["title"], "历史补录")
        self.assertTrue(workout["finished"])
        self.assertEqual(workout["training_time"], "")
        self.assertEqual(workout["body_parts"], ["胸", "背"])
        self.assertTrue(
            all(
                entry["completed"]
                for exercise in workout["exercises"]
                for entry in exercise["set_log"]
            )
        )
        self.assertEqual(self.store.data["rest_days"], [])
        with self.assertRaises(ValueError):
            self.store.add_historical_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 1, "reps": 1, "weight": 1},
            )

    def test_restoring_backup_keeps_snapshot_and_rejects_invalid_document(self):
        workout = self.store.add_daily_exercise(
            "2026-11-19",
            "胸",
            {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
        )
        empty_backup = {
            "version": 2,
            "plans": [],
            "workouts": [],
            "body_weights": [],
            "rest_days": [],
        }

        snapshot = self.store.restore_backup(empty_backup)

        self.assertIsNotNone(snapshot)
        self.assertTrue(snapshot.exists())
        saved_before_restore = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(saved_before_restore["workouts"][0]["id"], workout["id"])
        self.assertEqual(self.store.data["workouts"], [])
        with self.assertRaises(ValueError):
            self.store.restore_backup({"version": 99})
        self.assertEqual(self.store.data["workouts"], [])

    def test_rest_day_and_calendar_summary_are_consistent(self):
        workout = self.store.add_daily_exercise(
            "2026-11-19",
            "胸",
            {"name": "卧推", "sets": 4, "reps": 8, "weight": 60},
        )
        self.assertEqual(workout["body_parts"], ["胸"])
        with self.assertRaisesRegex(ValueError, "已有训练记录"):
            self.store.set_rest_day("2026-11-19", True)
        self.store.set_rest_day("2026-11-20", True)
        self.assertTrue(self.store.calendar_summary("2026-11")["2026-11-20"]["is_rest_day"])

    def test_personal_records_use_the_highest_weight_and_latest_date(self):
        exercise = {"name": "卧推", "sets": 4, "reps": 8, "weight": 60}
        self.store.add_workout("2026-11-18", "训练", ["胸"], [exercise])
        self.store.add_workout(
            "2026-11-19",
            "训练",
            ["胸"],
            [{**exercise, "weight": 70}],
        )

        self.assertEqual(
            self.store.personal_records(),
            [{"name": "卧推", "weight": 70.0, "date": "2026-11-19"}],
        )

    def test_set_log_tracks_completion_and_finishes_daily_workout(self):
        workout = self.store.add_daily_exercise(
            "2026-11-19",
            "胸",
            {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
        )
        self.assertEqual(
            [entry["completed"] for entry in workout["exercises"][0]["set_log"]],
            [False, False],
        )
        self.store.update_workout_set(
            workout["id"],
            0,
            0,
            completed=True,
            weight=65,
        )
        self.store.add_workout_set(workout["id"], 0)
        finished = self.store.finish_workout("2026-11-19")

        self.assertTrue(finished["finished"])
        self.assertEqual(
            [entry["completed"] for entry in finished["exercises"][0]["set_log"]],
            [True, False, False],
        )
        self.assertEqual(self.store.personal_records()[0]["weight"], 65.0)

    def test_reopening_finished_workout_restores_active_state(self):
        workout = self.store.add_daily_exercise(
            "2026-11-19",
            "胸",
            {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
        )
        self.store.update_workout_set(
            workout["id"],
            0,
            0,
            completed=True,
        )
        finished = self.store.finish_workout("2026-11-19")
        reopened = self.store.reopen_workout(workout["id"])

        self.assertTrue(finished["finished"])
        self.assertFalse(reopened["finished"])
        self.assertNotIn("duration_seconds", reopened)
        self.assertIsNotNone(self.store.active_workout("2026-11-19"))
        self.assertTrue(reopened["exercises"][0]["set_log"][0]["completed"])

    def test_reopening_workout_rejects_another_active_session_on_same_day(self):
        finished = self.store.add_workout(
            "2026-11-19",
            "已结束训练",
            ["胸"],
            [{"name": "卧推", "sets": 2, "reps": 8, "weight": 60}],
        )
        self.store.add_daily_exercise(
            "2026-11-19",
            "背",
            {"name": "划船", "sets": 2, "reps": 8, "weight": 40},
        )

        with self.assertRaisesRegex(ValueError, "另一条进行中的训练"):
            self.store.reopen_workout(finished["id"])

    def test_pausing_workout_excludes_paused_time_from_duration(self):
        with patch("fitness_data.time.time", return_value=1000):
            workout = self.store.add_daily_exercise(
                "2026-11-19",
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
        with patch("fitness_data.time.time", return_value=1060):
            paused = self.store.pause_workout(workout["id"])

        self.assertEqual(paused["duration_seconds"], 60)
        self.assertEqual(paused["paused_at"], 1060)
        persisted_pause = FitnessStore(self.path).data["workouts"][0]
        self.assertEqual(persisted_pause["duration_seconds"], 60)
        self.assertEqual(persisted_pause["paused_at"], 1060)

        with patch("fitness_data.time.time", return_value=1660):
            resumed = self.store.resume_workout(workout["id"])
        self.assertNotIn("paused_at", resumed)
        self.assertNotIn("duration_seconds", resumed)

        with patch("fitness_data.time.time", return_value=1720):
            finished = self.store.finish_workout("2026-11-19")
        self.assertEqual(finished["duration_seconds"], 120)
        self.assertNotIn("paused_at", finished)
        with patch("fitness_data.time.time", return_value=1800):
            reopened_paused = self.store.reopen_workout(workout["id"], paused=True)
        self.assertEqual(reopened_paused["duration_seconds"], 120)
        self.assertIsNotNone(reopened_paused["paused_at"])

    def test_reordering_exercises_preserves_each_exercise_record(self):
        workout = self.store.add_daily_exercises(
            "2026-11-19",
            ["胸", "背"],
            [
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
                {"name": "划船", "sets": 3, "reps": 10, "weight": 40},
            ],
        )
        self.store.update_workout_set(
            workout["id"],
            1,
            0,
            completed=True,
            weight=45,
        )

        self.store.move_workout_exercise(workout["id"], 0, 1)

        exercises = FitnessStore(self.path).data["workouts"][0]["exercises"]
        self.assertEqual([item["name"] for item in exercises], ["划船", "卧推"])
        self.assertEqual(exercises[0]["set_log"][0]["weight"], 45.0)
        self.assertTrue(exercises[0]["set_log"][0]["completed"])

    def test_deleted_historical_workout_can_be_restored(self):
        workout = self.store.add_workout(
            "2026-11-19",
            "上肢训练",
            ["胸", "背"],
            [{"name": "卧推", "sets": 2, "reps": 8, "weight": 60}],
        )
        self.store.delete("workouts", workout["id"])

        self.store.restore_workout(workout)

        restored = FitnessStore(self.path).data["workouts"]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["id"], workout["id"])
        self.assertEqual(restored[0]["title"], "上肢训练")


if __name__ == "__main__":
    unittest.main()
