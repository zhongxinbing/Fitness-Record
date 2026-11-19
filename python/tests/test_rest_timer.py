import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fitness_ui.rest_timer import (
    RestTimerController,
    RestTimerError,
    read_timer_state,
    write_timer_state,
)


class RestTimerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "rest_timer.json"
        self.app = Mock()
        self.controller = RestTimerController(self.app, self.path)

    def tearDown(self):
        self.controller.cancel()
        self.temp_dir.cleanup()

    def test_start_persists_timer_and_cancel_stops_it(self):
        with patch("fitness_ui.rest_timer.platform", "linux"):
            self.controller.start("卧推", 30)

            state = read_timer_state(self.path)
            self.assertEqual(state["exercise"], "卧推")
            self.assertEqual(state["status"], "running")
            self.assertGreater(state["deadline"], 0)

            self.controller.cancel()

        self.assertEqual(read_timer_state(self.path)["status"], "cancelled")
        self.assertIsNone(self.controller.state)

    def test_rejects_invalid_duration_without_writing_state(self):
        with patch("fitness_ui.rest_timer.platform", "linux"):
            for duration in (0, -1, 3601, True):
                with self.subTest(duration=duration):
                    with self.assertRaises(RestTimerError):
                        self.controller.start("卧推", duration)

        self.assertFalse(self.path.exists())

    def test_extend_persists_additional_time_to_running_timer(self):
        with patch("fitness_ui.rest_timer.platform", "linux"):
            self.controller.start("卧推", 60)
            old_deadline = self.controller.state["deadline"]

            self.controller.extend(30)

        self.assertEqual(self.controller.state["duration"], 90)
        self.assertAlmostEqual(self.controller.state["deadline"], old_deadline + 30)
        self.assertEqual(read_timer_state(self.path)["duration"], 90)

    def test_android_start_requires_permissions_and_starts_service(self):
        with (
            patch("fitness_ui.rest_timer.platform", "android"),
            patch("fitness_ui.rest_timer.request_timer_permissions") as permissions,
            patch("fitness_ui.rest_timer.start_background_service") as service,
        ):
            self.controller.start("深蹲", 45)

        permissions.assert_called_once_with()
        service.assert_called_once()
        self.assertEqual(service.call_args.args[0]["state_path"], str(self.path))

    def test_refresh_notifies_for_completed_timer(self):
        write_timer_state(
            self.path,
            {
                "id": "completed-id",
                "exercise": "硬拉",
                "deadline": 1,
                "status": "completed",
                "notified": True,
            },
        )

        with patch("fitness_ui.rest_timer.platform", "linux"):
            self.controller.refresh()

        self.app.on_rest_timer_finished.assert_called_once_with("硬拉")
        self.assertIsNone(read_timer_state(self.path))

    def test_restore_cleans_up_completed_timer(self):
        write_timer_state(
            self.path,
            {
                "id": "completed-id",
                "exercise": "划船",
                "deadline": 1,
                "status": "completed",
                "notified": False,
            },
        )

        with patch("fitness_ui.rest_timer.platform", "linux"):
            self.controller.restore()

        self.app.on_rest_timer_finished.assert_called_once_with("划船")
        self.assertIsNone(read_timer_state(self.path))

    def test_reports_corrupt_timer_state(self):
        self.path.write_text("{", encoding="utf-8")

        with self.assertRaises(RestTimerError):
            read_timer_state(self.path)


if __name__ == "__main__":
    unittest.main()
