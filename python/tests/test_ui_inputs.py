import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from fitness_data import FitnessStore
from fitness_ui.app import FitnessRecordApp
from fitness_ui.dialogs import (
    ExerciseEditorPopup,
    ExerciseEntryPopup,
    WorkoutDetailsPopup,
)
from fitness_ui.screens import (
    CalendarHistoryScreen,
    ExerciseLogCard,
    LibraryScreen,
    WorkoutScreen,
)
from fitness_ui.widgets import (
    AppButton,
    FitnessScreen,
    make_input,
    make_scroll_content,
)


class TextInputTests(unittest.TestCase):
    def test_rest_timer_snapshot_is_safe_before_app_initialization(self):
        app = FitnessRecordApp()

        self.assertEqual(app.rest_timer_snapshot(), (None, 0))

    def test_initial_workout_screen_enters_after_timer_controller_is_created(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(
                    FitnessRecordApp,
                    "user_data_dir",
                    new_callable=PropertyMock,
                    return_value=temp_dir,
                ),
                patch("fitness_ui.app.Clock.schedule_once"),
            ):
                app = FitnessRecordApp()
                app.build()
                app.workout_screen.on_pre_enter()

        self.assertIsNotNone(app.timer_controller)

    def _insert_text(self, field, text):
        Window.add_widget(field)
        Clock.tick()
        try:
            field.focus = True
            field.insert_text(text)
            Clock.tick()
        finally:
            Window.remove_widget(field)
        return field

    def test_text_input_accepts_chinese_with_text_ime(self):
        field = self._insert_text(make_input("动作名称"), "杠铃卧推")

        self.assertEqual(field.input_type, "text")
        self.assertTrue(field.keyboard_suggestions)
        self.assertEqual(field.text, "杠铃卧推")

    def test_numeric_input_keeps_numeric_filter(self):
        field = self._insert_text(make_input("重量 kg", numeric=True), "42.5")

        self.assertEqual(field.input_filter, "float")
        self.assertEqual(field.text, "42.5")

    def test_action_sheet_adds_a_chosen_exercise_and_part(self):
        on_add = Mock(return_value=True)
        on_save_template = Mock(return_value=True)
        popup = ExerciseEntryPopup(on_add, on_save_template)
        popup.name_input.text = "卧推"
        popup.weight_input.text = "60"
        popup.sets_input.text = "4"
        popup.reps_input.text = "8"
        popup.rest_input.text = "90"
        popup.select_part("胸")

        popup.confirm_add()

        on_add.assert_called_once_with(
            {
                "name": "卧推",
                "sets": 4,
                "reps": 8,
                "weight": 60.0,
                "rest_seconds": 90,
                "alternatives": [],
            },
            "胸",
        )

    def test_workout_set_rows_toggle_completion(self):
        on_edit = Mock()
        on_rest = Mock()
        on_toggle = Mock()
        on_add_set = Mock()
        card = ExerciseLogCard(
            {
                "name": "卧推",
                "sets": 2,
                "reps": 8,
                "weight": 60,
                "rest_seconds": 90,
                "set_log": [
                    {"weight": 60, "reps": 8, "completed": False},
                    {"weight": 60, "reps": 8, "completed": True},
                ],
            },
            [{"weight": 55, "reps": 8}],
            is_record=False,
            finished=False,
            on_edit=on_edit,
            on_rest=on_rest,
            on_toggle_set=on_toggle,
            on_edit_set=Mock(),
            on_add_set=on_add_set,
        )
        check = next(
            widget
            for widget in card.walk()
            if isinstance(widget, AppButton) and widget.text == "开始计时"
        )
        self.assertGreaterEqual(check.height, 44)

        check.dispatch("on_release")

        on_toggle.assert_called_once_with(0, True)
        next(
            widget
            for widget in card.walk()
            if isinstance(widget, AppButton) and widget.text == "休息 90 秒"
        ).dispatch("on_release")
        next(
            widget
            for widget in card.walk()
            if isinstance(widget, AppButton) and widget.text == "+ 添加一组"
        ).dispatch("on_release")
        on_rest.assert_called_once_with()
        on_add_set.assert_called_once_with()
        self.assertTrue(
            any(
                isinstance(widget, AppButton) and widget.text == "已完成"
                for widget in card.walk()
            )
        )
        card.update_rest_timer(45)
        self.assertEqual(card.rest_button.text, "剩余 00:45")
        card.update_rest_timer(None)
        self.assertEqual(card.rest_button.text, "休息 90 秒")
        self.assertGreaterEqual(card.rest_button.height, 44)
        self.assertFalse(
            any(
                isinstance(widget, AppButton) and widget.text == "删除"
                for widget in card.walk()
            )
        )
        self.assertTrue(
            any(
                getattr(widget, "text", "").startswith("已完成 1/2 组 · 训练量 480 kg")
                for widget in card.walk()
            )
        )

    def test_workout_details_popup_saves_title_and_chinese_notes(self):
        on_save = Mock(return_value=True)
        popup = WorkoutDetailsPopup("今日训练", "", on_save)
        popup.title_input.text = "周一推训练"
        popup.notes_input.text = "状态很好，卧推感觉稳定"

        popup.save()

        on_save.assert_called_once_with("周一推训练", "状态很好，卧推感觉稳定")

    def test_exercise_removal_requires_confirmation(self):
        on_delete = Mock()
        editor = ExerciseEditorPopup(
            {
                "name": "卧推",
                "sets": 3,
                "reps": 8,
                "weight": 60,
                "rest_seconds": 90,
                "alternatives": [],
            },
            Mock(),
            on_delete,
        )

        with patch("fitness_ui.dialogs.ConfirmActionPopup") as confirm_popup:
            editor.delete()

        confirm_popup.assert_called_once()
        confirm_popup.return_value.open.assert_called_once_with()
        on_delete.assert_not_called()
        confirm_popup.call_args.args[3]()
        on_delete.assert_called_once_with()

    def test_reducing_exercise_sets_requires_confirmation(self):
        on_save = Mock()
        editor = ExerciseEditorPopup(
            {
                "name": "卧推",
                "sets": 3,
                "reps": 8,
                "weight": 60,
                "rest_seconds": 90,
                "alternatives": [],
                "set_log": [
                    {"weight": 60, "reps": 8, "completed": True},
                    {"weight": 60, "reps": 8, "completed": False},
                    {"weight": 60, "reps": 8, "completed": False},
                ],
            },
            on_save,
        )
        editor.sets_input.text = "2"

        with patch("fitness_ui.dialogs.ConfirmActionPopup") as confirm_popup:
            editor.save()

        on_save.assert_not_called()
        self.assertIn("移除最后 1 组", confirm_popup.call_args.args[1])
        confirm_popup.call_args.args[3]()
        on_save.assert_called_once()
        self.assertEqual(on_save.call_args.args[0]["sets"], 2)

    def test_today_screen_shows_persisted_session_details_and_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
            screen = WorkoutScreen(SimpleNamespace(store=store))
            screen.refresh_today()

            self.assertEqual(screen.session_title.text, "今日训练")
            self.assertTrue(screen.session_duration.text.startswith("训练时长 "))
            self.assertEqual(screen.display_workout_id, workout["id"])
            self.assertTrue(
                any(
                    getattr(widget, "text", "").startswith("已完成 0/2 组")
                    for widget in screen.content.walk()
                )
            )
            card = screen.exercise_cards[0]
            screen.update_rest_timer(
                {"status": "running", "exercise": "卧推"},
                45,
            )
            self.assertEqual(card.rest_button.text, "剩余 00:45")
            screen.update_rest_timer(None, 0)
            self.assertEqual(card.rest_button.text, "休息 60 秒")

            self.assertTrue(
                screen._save_workout_details(workout["id"], "周一推训练", "状态不错")
            )
            self.assertEqual(screen.session_title.text, "周一推训练")
            self.assertEqual(screen.session_notes.text, "状态不错")

    def test_tapping_rest_during_a_running_timer_reopens_that_timer(self):
        controller = Mock()
        controller.state = {"status": "running", "exercise": "高位下拉"}
        app = SimpleNamespace(
            store=Mock(),
            timer_controller=controller,
            open_rest_timer=Mock(),
        )
        screen = WorkoutScreen(app)

        screen.start_rest_timer({"name": "高位下拉", "rest_seconds": 60})

        controller.start.assert_not_called()
        app.open_rest_timer.assert_called_once_with()

    def test_start_set_button_marks_set_done_and_starts_rest_timer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "背",
                {"name": "高位下拉", "sets": 2, "reps": 15, "weight": 20},
            )
            controller = Mock()
            controller.state = None
            app = SimpleNamespace(
                store=store,
                timer_controller=controller,
                open_rest_timer=Mock(),
                rest_timer_snapshot=lambda: (None, 0),
            )
            screen = WorkoutScreen(app)
            screen.refresh_today()
            next(
                widget
                for widget in screen.exercise_cards[0].walk()
                if isinstance(widget, AppButton) and widget.text == "开始计时"
            ).dispatch("on_release")

            self.assertTrue(store.data["workouts"][0]["exercises"][0]["set_log"][0]["completed"])
            self.assertTrue(
                any(
                    isinstance(widget, AppButton) and widget.text == "已完成"
                    for widget in screen.exercise_cards[0].walk()
                )
            )
            controller.start.assert_called_once_with("高位下拉", 60)
            app.open_rest_timer.assert_called_once_with()

    def test_finishing_workout_requires_confirmation_when_sets_are_incomplete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
            screen = WorkoutScreen(SimpleNamespace(store=store))
            screen.notify = Mock()

            with patch("fitness_ui.screens.ConfirmActionPopup") as confirm_popup:
                screen.finish_workout()

            message = confirm_popup.call_args.args[1]
            self.assertIn("还有 2 组未完成", message)
            self.assertFalse(store.active_workout(date.today().isoformat())["finished"])
            confirm_popup.call_args.args[3]()
            self.assertTrue(
                next(
                    item
                    for item in store.data["workouts"]
                    if item["id"] == workout["id"]
                )["finished"]
            )

    def test_history_shows_each_set_notes_and_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
            store.update_workout_set(
                workout["id"],
                0,
                0,
                weight=65,
                reps=9,
                completed=True,
            )
            store.update_workout_details(workout["id"], "周日推训练", "状态很好")
            stored_workout = next(
                item for item in store.data["workouts"] if item["id"] == workout["id"]
            )
            stored_workout["started_at"] = time.time() - 3665
            store.finish_workout(date.today().isoformat())
            next(
                item for item in store.data["workouts"] if item["id"] == workout["id"]
            )["duration_seconds"] = 3665

            screen = CalendarHistoryScreen(SimpleNamespace(store=store))
            screen.render()
            texts = [
                widget.text
                for widget in screen.content.walk()
                if isinstance(widget, Label)
            ]

        self.assertIn("第 1 组 · 65kg × 9次 · 已完成", texts)
        self.assertIn("第 2 组 · 60kg × 8次 · 未完成", texts)
        self.assertIn("备注：状态很好", texts)
        self.assertIn("训练时长 01:01:05", texts)

    def test_template_search_filters_and_delete_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            store.add_plan(
                "推胸日",
                ["胸"],
                [{"name": "卧推", "sets": 3, "reps": 8, "weight": 60}],
            )
            leg_template = store.add_plan(
                "腿部训练",
                ["腿"],
                [{"name": "深蹲", "sets": 4, "reps": 8, "weight": 80}],
            )
            screen = LibraryScreen(SimpleNamespace(store=store))
            screen.template_search.text = "深蹲"
            template_texts = [
                widget.text
                for widget in screen.template_list.walk()
                if isinstance(widget, Label)
            ]
            self.assertTrue(any("腿部训练" in text for text in template_texts))
            self.assertFalse(any("推胸日" in text for text in template_texts))

            with patch("fitness_ui.screens.ConfirmActionPopup") as confirm_popup:
                screen.delete_template(leg_template["id"])

            self.assertEqual(len(store.data["plans"]), 2)
            self.assertIn("腿部训练", confirm_popup.call_args.args[1])
            confirm_popup.call_args.args[3]()
            self.assertEqual(
                [item["title"] for item in store.data["plans"]],
                ["推胸日"],
            )

    def test_page_scroll_tracks_screen_size(self):
        screen = FitnessScreen(Mock())
        scroll, content = make_scroll_content()
        first = Widget(size_hint_y=None, height=40)
        second = Widget(size_hint_y=None, height=40)
        content.add_widget(first)
        content.add_widget(second)

        screen.add_page_scroll(scroll)
        screen.size = (320, 600)
        screen.pos = (0, 0)
        Clock.tick()

        self.assertEqual(scroll.size, screen.size)
        self.assertEqual(scroll.pos, screen.pos)
        self.assertEqual(scroll.scroll_y, 1)
        self.assertEqual(content.width, scroll.width)
        self.assertAlmostEqual(first.width, content.width - 32)
        self.assertGreater(first.y, second.y)


if __name__ == "__main__":
    unittest.main()
