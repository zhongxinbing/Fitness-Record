import tempfile
import unittest
from pathlib import Path

from fitness_data import FitnessStore


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


if __name__ == "__main__":
    unittest.main()
