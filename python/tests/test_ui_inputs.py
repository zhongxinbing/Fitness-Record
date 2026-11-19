import unittest
from unittest.mock import Mock

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.widget import Widget

from fitness_ui.dialogs import ExerciseEntryPopup
from fitness_ui.screens import ExerciseLogCard
from fitness_ui.widgets import (
    AppButton,
    FitnessScreen,
    make_input,
    make_scroll_content,
)


class TextInputTests(unittest.TestCase):
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
                    {"weight": 60, "reps": 8, "completed": False},
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
            on_delete=Mock(),
        )
        check = next(
            widget
            for widget in card.walk()
            if isinstance(widget, AppButton) and widget.text == "○"
        )

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
