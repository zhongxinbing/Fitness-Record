import json
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from fitness_data import FitnessStore
from fitness_ui.app import FitnessRecordApp, RestTimerPopup
from fitness_ui.dialogs import (
    BackupImportPopup,
    ExerciseEditorPopup,
    ExerciseEntryPopup,
    WorkoutTemplatePreviewPopup,
    WorkoutDetailsPopup,
    WorkoutTemplateEditorPopup,
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
        cancel = next(
            widget
            for widget in popup.walk()
            if isinstance(widget, AppButton) and widget.text == "取消"
        )
        popup.dismiss = Mock()
        cancel.dispatch("on_release")
        popup.dismiss.assert_called_once_with()

    def test_action_sheet_requires_confirmation_for_duplicate_exercises(self):
        on_add = Mock(return_value=True)
        popup = ExerciseEntryPopup(
            on_add,
            Mock(return_value=True),
            find_duplicates=lambda _exercise, _part: ["卧推"],
        )
        popup.name_input.text = "卧推"
        popup.weight_input.text = "60"
        popup.sets_input.text = "4"
        popup.reps_input.text = "8"
        popup.rest_input.text = "90"

        with patch("fitness_ui.dialogs.ConfirmActionPopup") as confirm_popup:
            popup.confirm_add()

        on_add.assert_not_called()
        self.assertIn("卧推", confirm_popup.call_args.args[1])
        confirm_popup.call_args.args[3]()
        on_add.assert_called_once()

    def test_workout_set_rows_toggle_completion(self):
        on_edit = Mock()
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
            if isinstance(widget, AppButton) and widget.text == "+ 添加一组"
        ).dispatch("on_release")
        on_add_set.assert_called_once_with()
        self.assertTrue(
            any(
                isinstance(widget, AppButton) and widget.text == "已完成"
                for widget in card.walk()
            )
        )
        card.update_rest_timer(45, 0)
        self.assertEqual(card.set_buttons[0].text, "00:45\n点击结束")
        self.assertEqual(card.set_buttons[1].text, "已完成")
        card.update_rest_timer(None)
        self.assertEqual(card.set_buttons[0].text, "开始计时")
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

    def test_removing_last_exercise_warns_that_the_workout_will_be_deleted(self):
        editor = ExerciseEditorPopup(
            {
                "name": "卧推",
                "sets": 1,
                "reps": 8,
                "weight": 60,
                "rest_seconds": 90,
                "alternatives": [],
            },
            Mock(),
            Mock(),
            deleting_last_exercise=True,
        )

        with patch("fitness_ui.dialogs.ConfirmActionPopup") as confirm_popup:
            editor.delete()

        self.assertIn("整次训练", confirm_popup.call_args.args[0])
        self.assertIn("训练名称、备注和时长", confirm_popup.call_args.args[1])
        self.assertEqual(confirm_popup.call_args.args[2], "删除整次训练")

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
            self.assertEqual(screen.session_edit_button.text, "详情")
            self.assertTrue(screen.session_duration.text.startswith("训练时长 "))
            self.assertEqual(screen.display_workout_id, workout["id"])
            self.assertTrue(
                any(
                    getattr(widget, "text", "").startswith("已完成 0/2 组")
                    for widget in screen.content.walk()
                )
            )
            card = screen.exercise_cards[0]
            screen._rest_timer_target = (workout["id"], 0, 0)
            screen.update_rest_timer(
                {"status": "running", "exercise": "卧推"},
                45,
            )
            self.assertEqual(card.set_buttons[0].text, "00:45\n点击结束")
            self.assertFalse(any(
                getattr(widget, "text", "") == "打开计时"
                for widget in screen.walk()
            ))
            screen.update_rest_timer(None, 0)
            self.assertEqual(card.set_buttons[0].text, "开始计时")

            self.assertTrue(
                screen._save_workout_details(workout["id"], "周一推训练", "状态不错")
            )
            self.assertEqual(screen.session_title.text, "周一推训练")
            self.assertEqual(screen.session_notes.text, "状态不错")

    def test_restored_timer_appears_on_matching_completed_set_button(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "背",
                {"name": "高位下拉", "sets": 2, "reps": 12, "weight": 30},
            )
            store.update_workout_set(workout["id"], 0, 0, completed=True)
            timer_state = {"status": "running", "exercise": "高位下拉"}
            screen = WorkoutScreen(
                SimpleNamespace(
                    store=store,
                    rest_timer_snapshot=lambda: (timer_state, 37),
                )
            )
            screen.refresh_today()

        self.assertEqual(screen._rest_timer_target, (workout["id"], 0, 0))
        self.assertEqual(screen.exercise_cards[0].set_buttons[0].text, "00:37\n点击结束")
        self.assertEqual(screen.exercise_cards[0].set_buttons[1].text, "开始计时")

    def test_minimizing_rest_timer_keeps_countdown_running(self):
        controller = Mock()
        controller.state = {"status": "running", "exercise": "卧推", "duration": 60}
        controller._remaining.return_value = 30
        popup = RestTimerPopup(
            SimpleNamespace(timer_controller=controller, timer_popup=None)
        )
        popup.dismiss = Mock()

        popup.minimize()

        popup.dismiss.assert_called_once_with()
        controller.cancel.assert_not_called()
        popup._restore_screensaver()

        app = FitnessRecordApp()
        app.workout_screen = Mock()
        app.timer_popup = None
        app.update_rest_timer(controller.state, 25)
        self.assertIsNone(app.timer_popup)
        app.workout_screen.update_rest_timer.assert_called_once_with(controller.state, 25)

    def test_tapping_rest_during_a_running_timer_does_not_open_a_popup(self):
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
        app.open_rest_timer.assert_not_called()

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
            screen.exercise_cards[0].set_buttons[0].dispatch("on_release")

            self.assertTrue(store.data["workouts"][0]["exercises"][0]["set_log"][0]["completed"])
            self.assertTrue(
                any(
                    isinstance(widget, AppButton) and widget.text == "已完成"
                    for widget in screen.exercise_cards[0].walk()
                )
            )
            controller.start.assert_called_once_with("高位下拉", 60)
            app.open_rest_timer.assert_not_called()
            controller.state = {"status": "running", "exercise": "高位下拉"}
            screen.update_rest_timer(controller.state, 45)
            self.assertEqual(
                screen.exercise_cards[0].set_buttons[0].text,
                "00:45\n点击结束",
            )
            screen.exercise_cards[0].set_buttons[0].dispatch("on_release")
            controller.cancel.assert_called_once_with()
            self.assertTrue(
                store.data["workouts"][0]["exercises"][0]["set_log"][0]["completed"]
            )
            screen.update_rest_timer(None, 0)
            self.assertEqual(screen.exercise_cards[0].set_buttons[0].text, "已完成")

    def test_template_shortcut_routes_selection_through_library_flow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            template = store.add_plan(
                "推胸日",
                ["胸"],
                [{"name": "卧推", "sets": 3, "reps": 8, "weight": 60}],
            )
            library_screen = SimpleNamespace(add_template_to_today=Mock())
            screen = WorkoutScreen(
                SimpleNamespace(store=store, library_screen=library_screen)
            )

            with patch("fitness_ui.screens.WorkoutTemplatePickerPopup") as picker:
                screen.open_template_picker()

            self.assertEqual(screen.template_button.text, "从模板开始")
            self.assertEqual(screen.add_action_button.text, "记录新动作")
            picker.assert_called_once()
            picker.call_args.args[1](template)
            library_screen.add_template_to_today.assert_called_once_with(template)

    def test_added_set_reuses_previous_values_and_scrolls_to_next_set(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {
                    "name": "卧推",
                    "sets": 2,
                    "reps": 8,
                    "weight": 60,
                    "rest_seconds": 0,
                },
            )
            screen = WorkoutScreen(
                SimpleNamespace(
                    store=store,
                    rest_timer_snapshot=lambda: (None, 0),
                    timer_controller=Mock(state=None),
                )
            )
            screen.refresh_today()

            with patch.object(screen.scroll, "scroll_to") as scroll_to:
                screen.add_set(workout["id"], 0)
                Clock.tick()

                added = store.data["workouts"][0]["exercises"][0]["set_log"][-1]
                self.assertEqual((added["weight"], added["reps"]), (60.0, 8))
                scroll_to.assert_called_once()
                self.assertIs(
                    scroll_to.call_args.args[0],
                    screen.exercise_cards[0].set_rows[2],
                )

                scroll_to.reset_mock()
                screen.toggle_set(
                    workout["id"],
                    0,
                    0,
                    True,
                    store.data["workouts"][0]["exercises"][0],
                )
                Clock.tick()
                scroll_to.assert_called_once()
                self.assertIs(
                    scroll_to.call_args.args[0],
                    screen.exercise_cards[0].set_rows[1],
                )

    def test_workout_can_be_paused_and_resumed_from_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
            screen = WorkoutScreen(SimpleNamespace(store=store))
            screen.refresh_today()

            screen.toggle_workout_pause()

            self.assertEqual(screen.header_title.text, "已暂停")
            self.assertEqual(screen.pause_button.text, "继续")
            self.assertIsNotNone(store.data["workouts"][0].get("paused_at"))

            screen.toggle_workout_pause()

            self.assertEqual(screen.pause_button.text, "暂停")
            self.assertNotIn("paused_at", store.data["workouts"][0])
            self.assertIsNotNone(store.active_workout(date.today().isoformat()))

    def test_exercise_order_can_be_changed_from_action_card(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercises(
                date.today().isoformat(),
                ["胸", "背"],
                [
                    {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
                    {"name": "划船", "sets": 2, "reps": 10, "weight": 40},
                ],
            )
            screen = WorkoutScreen(SimpleNamespace(store=store))
            screen.refresh_today()

            move_down = next(
                widget
                for widget in screen.exercise_cards[0].walk()
                if isinstance(widget, AppButton) and widget.text == "下移"
            )
            move_down.dispatch("on_release")

            self.assertEqual(
                [item["name"] for item in store.active_workout(workout["date"])["exercises"]],
                ["划船", "卧推"],
            )

    def test_recent_exercise_reopens_prefilled_form_with_unchecked_sets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            store.add_workout(
                "2026-11-19",
                "胸部训练",
                ["胸"],
                [{"name": "卧推", "sets": 2, "reps": 8, "weight": 60}],
            )
            screen = WorkoutScreen(SimpleNamespace(store=store))

            with patch("fitness_ui.screens.RecentExercisePickerPopup") as picker:
                screen.open_recent_action_picker()

            item = picker.call_args.args[0][0]
            self.assertEqual(item["exercise"]["name"], "卧推")
            with patch("fitness_ui.screens.ExerciseEntryPopup") as entry_popup:
                picker.call_args.args[1](item)

            entry_popup.assert_called_once()
            self.assertEqual(entry_popup.call_args.kwargs["initial_part"], "胸")
            self.assertTrue(
                all(
                    not item["completed"]
                    for item in entry_popup.call_args.kwargs["initial_exercise"]["set_log"]
                )
            )

    def test_reusing_recent_exercise_preserves_set_values_and_resets_completion(self):
        exercise = {
            "name": "卧推",
            "sets": 2,
            "reps": 8,
            "weight": 67.5,
            "rest_seconds": 90,
            "alternatives": [],
            "set_log": [
                {"weight": 65, "reps": 8, "completed": False},
                {"weight": 70, "reps": 6, "completed": True},
            ],
        }
        popup = ExerciseEntryPopup(
            Mock(return_value=True),
            Mock(return_value=True),
            initial_exercise=exercise,
            initial_part="胸",
        )

        values = popup._values()
        self.assertEqual(
            [(item["weight"], item["reps"], item["completed"]) for item in values["set_log"]],
            [(65, 8, False), (70, 6, False)],
        )
        popup.weight_input.text = "72.5"
        changed_values = popup._values()
        self.assertEqual(
            [(item["weight"], item["reps"]) for item in changed_values["set_log"]],
            [(72.5, 8), (72.5, 6)],
        )

    def test_rest_day_action_is_hidden_when_today_has_a_workout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
            screen = WorkoutScreen(SimpleNamespace(store=store))
            screen.refresh_today()

            self.assertFalse(
                any(
                    isinstance(widget, AppButton)
                    and widget.text == "今天太累，休息一天"
                    for widget in screen.content.walk()
                )
            )

    def test_deleted_last_action_can_be_undone_from_today_screen(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
            screen = WorkoutScreen(SimpleNamespace(store=store))

            screen.remove_exercise(workout["id"], 0)
            self.assertEqual(store.data["workouts"], [])

            screen.undo_banner.undo()
            self.assertEqual(store.data["workouts"][0]["id"], workout["id"])
            self.assertEqual(store.data["workouts"][0]["exercises"][0]["name"], "卧推")

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
            self.assertEqual(screen.undo_banner.message.text, "训练已结束")
            screen.undo_banner.undo()
            self.assertIsNotNone(store.active_workout(date.today().isoformat()))

    def test_undoing_another_set_keeps_active_timer_running(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_daily_exercise(
                date.today().isoformat(),
                "胸",
                {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
            )
            for set_index in (0, 1):
                store.update_workout_set(
                    workout["id"],
                    0,
                    set_index,
                    completed=True,
                )
            controller = Mock()
            controller.state = {"status": "running", "exercise": "卧推"}
            app = SimpleNamespace(
                store=store,
                timer_controller=controller,
                rest_timer_snapshot=lambda: (None, 0),
            )
            screen = WorkoutScreen(app)
            screen._rest_timer_target = (workout["id"], 0, 1)
            exercise = store.data["workouts"][0]["exercises"][0]

            screen.toggle_set(
                workout["id"],
                0,
                0,
                False,
                exercise,
            )

            self.assertFalse(
                store.data["workouts"][0]["exercises"][0]["set_log"][0]["completed"]
            )
            controller.cancel.assert_not_called()
            self.assertTrue(
                store.data["workouts"][0]["exercises"][0]["set_log"][1]["completed"]
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
            screen.undo_banner.undo()
            self.assertEqual(
                [item["title"] for item in store.data["plans"]],
                ["推胸日", "腿部训练"],
            )

    def test_library_can_create_and_edit_templates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            screen = LibraryScreen(SimpleNamespace(store=store))
            self.assertEqual(screen.add_template_button.text, "+")

            with patch("fitness_ui.screens.WorkoutTemplateEditorPopup") as editor:
                screen.create_template()
                create_callback = editor.call_args.args[1]
                create_callback(
                    "推胸日",
                    ["胸"],
                    [{"name": "卧推", "sets": 3, "reps": 8, "weight": 40}],
                )

            template = store.data["plans"][0]
            self.assertEqual(template["title"], "推胸日")
            self.assertEqual(template["exercises"][0]["name"], "卧推")
            self.assertEqual(len(screen.template_list.children), 1)

            with patch("fitness_ui.screens.WorkoutTemplateEditorPopup") as editor:
                screen.edit_template(template["id"])
                edit_callback = editor.call_args.args[1]
                edit_callback(
                    "上肢力量",
                    ["背"],
                    [{"name": "划船", "sets": 4, "reps": 10, "weight": 35}],
                )

            persisted = FitnessStore(store.path).data["plans"][0]
            self.assertEqual(persisted["id"], template["id"])
            self.assertEqual(persisted["title"], "上肢力量")
            self.assertEqual(persisted["body_parts"], ["背"])
            self.assertEqual(persisted["exercises"][0]["name"], "划船")

    def test_template_editor_manages_multiple_configured_exercises(self):
        on_save = Mock(return_value=True)
        popup = WorkoutTemplateEditorPopup(None, on_save)
        popup.title_input.text = "上肢训练"
        popup.toggle_part("背")
        popup._append_exercise(
            {"name": "卧推", "sets": 3, "reps": 8, "weight": 40},
            "胸",
        )
        popup._append_exercise(
            {"name": "划船", "sets": 4, "reps": 10, "weight": 35},
            "背",
        )
        with patch("fitness_ui.dialogs.ExerciseEditorPopup") as editor:
            popup._edit_exercise(0)
            editor.call_args.args[1](
                {"name": "上斜卧推", "sets": 4, "reps": 8, "weight": 30}
            )
        popup._remove_exercise(1)
        popup.save()

        on_save.assert_called_once_with(
            "上肢训练",
            ["胸", "背"],
            [{"name": "上斜卧推", "sets": 4, "reps": 8, "weight": 30}],
        )

    def test_adding_template_after_completed_session_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            today = date.today().isoformat()
            store.add_workout(
                today,
                "已完成训练",
                ["胸"],
                [{"name": "卧推", "sets": 2, "reps": 8, "weight": 60}],
            )
            template = store.add_plan(
                "拉背日",
                ["背"],
                [{"name": "划船", "sets": 3, "reps": 10, "weight": 40}],
            )
            app = SimpleNamespace(
                store=store,
                workout_screen=SimpleNamespace(refresh_today=Mock()),
            )
            screen = LibraryScreen(app)

            with (
                patch("fitness_ui.screens.WorkoutTemplatePreviewPopup") as preview_popup,
                patch("fitness_ui.screens.ConfirmActionPopup") as confirm_popup,
            ):
                screen.add_template_to_today(template)
                self.assertIsNone(store.active_workout(today))
                preview_popup.call_args.args[2]()

            self.assertIsNone(store.active_workout(today))
            self.assertIn("新建一条训练记录", confirm_popup.call_args.args[1])
            confirm_popup.call_args.args[3]()
            self.assertIsNotNone(store.active_workout(today))

    def test_template_preview_lists_actions_and_warns_about_duplicates(self):
        template = {
            "title": "推胸日",
            "body_parts": ["胸"],
            "exercises": [
                {"name": "卧推", "sets": 4, "reps": 8, "weight": 60, "rest_seconds": 90},
                {"name": "飞鸟", "sets": 3, "reps": 12, "weight": 15, "rest_seconds": 60},
            ],
        }
        popup = WorkoutTemplatePreviewPopup(template, ["卧推"], Mock())
        labels = [
            widget.text
            for widget in popup.walk()
            if isinstance(widget, Label)
        ]
        buttons = [
            widget.text
            for widget in popup.walk()
            if isinstance(widget, AppButton)
        ]

        self.assertIn("1. 卧推", labels)
        self.assertIn("2. 飞鸟", labels)
        self.assertTrue(any("继续添加会重复" in text for text in labels))
        self.assertIn("仍要添加", buttons)

    def test_history_can_edit_sets_and_undo_workout_deletion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            workout = store.add_workout(
                date.today().isoformat(),
                "今日训练",
                ["胸"],
                [{"name": "卧推", "sets": 2, "reps": 8, "weight": 60}],
            )
            screen = CalendarHistoryScreen(SimpleNamespace(store=store))
            screen.render()

            with patch("fitness_ui.screens.SetEntryPopup") as edit_popup:
                screen.edit_historical_set(
                    workout["id"],
                    0,
                    0,
                    store.data["workouts"][0]["exercises"][0]["set_log"][0],
                )
                edit_popup.call_args.args[2](65, 9)

            self.assertEqual(
                store.data["workouts"][0]["exercises"][0]["set_log"][0]["weight"],
                65.0,
            )
            with patch("fitness_ui.screens.ConfirmActionPopup") as confirm_popup:
                screen.delete_historical_workout(workout["id"])
                confirm_popup.call_args.args[3]()

            self.assertEqual(store.data["workouts"], [])
            screen.undo_banner.undo()
            self.assertEqual(store.data["workouts"][0]["id"], workout["id"])
    def test_adding_template_previews_and_detects_existing_action_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            today = date.today().isoformat()
            store.add_daily_exercise(
                today,
                "胸",
                {"name": "卧推", "sets": 3, "reps": 8, "weight": 60},
            )
            template = store.add_plan(
                "推胸日",
                ["胸"],
                [
                    {"name": "卧推", "sets": 4, "reps": 8, "weight": 65},
                    {"name": "飞鸟", "sets": 3, "reps": 12, "weight": 15},
                ],
            )
            screen = LibraryScreen(
                SimpleNamespace(
                    store=store,
                    workout_screen=SimpleNamespace(refresh_today=Mock()),
                )
            )

            with patch("fitness_ui.screens.WorkoutTemplatePreviewPopup") as preview_popup:
                screen.add_template_to_today(template)
                self.assertEqual(preview_popup.call_args.args[1], ["卧推"])
                self.assertEqual(len(store.active_workout(today)["exercises"]), 1)
                preview_popup.call_args.args[2]()

            self.assertEqual(
                [item["name"] for item in store.active_workout(today)["exercises"]],
                ["卧推", "卧推", "飞鸟"],
            )

    def test_history_can_backfill_a_past_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            screen = CalendarHistoryScreen(SimpleNamespace(store=store))
            screen.selected_date = yesterday

            with patch("fitness_ui.screens.ExerciseEntryPopup") as entry_popup:
                screen.open_backfill()

            self.assertEqual(entry_popup.call_count, 1)
            self.assertTrue(
                entry_popup.call_args.kwargs["on_add"](
                    {"name": "卧推", "sets": 2, "reps": 8, "weight": 60},
                    "胸",
                )
            )
            self.assertEqual(store.data["workouts"][0]["date"], yesterday)
            self.assertTrue(store.data["workouts"][0]["finished"])

    def test_backup_restore_popup_previews_validated_data(self):
        popup = BackupImportPopup(
            FitnessStore.validate_backup_document,
            Mock(),
        )
        popup.data_input.text = json.dumps({
            "version": 2,
            "plans": [],
            "workouts": [],
            "body_weights": [],
            "rest_days": [],
        })

        with patch("fitness_ui.dialogs.ConfirmActionPopup") as confirm_popup:
            popup.submit()

        self.assertIn("0 次训练", confirm_popup.call_args.args[1])
        self.assertIn("替换本机全部数据", confirm_popup.call_args.args[1])

    def test_backup_restore_exports_current_data_before_replacing_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FitnessStore(Path(temp_dir) / "records.json")
            store.add_workout(
                "2026-11-19",
                "当前训练",
                ["胸"],
                [{"name": "卧推", "sets": 2, "reps": 8, "weight": 60}],
            )
            app = SimpleNamespace(
                store=store,
                user_data_dir=temp_dir,
            )
            screen = CalendarHistoryScreen(app)
            screen.notify = Mock()
            document = {
                "version": 2,
                "plans": [],
                "workouts": [],
                "body_weights": [],
                "rest_days": [],
            }

            with patch(
                "fitness_ui.screens.export_json",
                return_value=Path(temp_dir) / "pre_restore.json",
            ) as export:
                screen._restore_backup(document)

            export.assert_called_once()
            self.assertEqual(export.call_args.args[0]["workouts"][0]["title"], "当前训练")
            self.assertEqual(export.call_args.args[1], temp_dir)
            self.assertEqual(store.data["workouts"], [])

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
