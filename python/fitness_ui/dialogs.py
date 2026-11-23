"""Dialogs for editing actions and selecting replacement exercises."""

from __future__ import annotations

import math
import re
from typing import Any, Callable

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from fitness_ui.theme import BORDER, DANGER, MUTED, SURFACE, TEXT, font_name
from fitness_ui.widgets import AppToggleButton, make_button, make_input, make_label


def _style_popup(popup: Popup) -> None:
    popup.background = ""
    popup.background_color = SURFACE
    popup.title_color = TEXT
    popup.title_font = font_name()
    popup.title_size = dp(18)
    popup.separator_color = BORDER


def parse_alternatives(value: str, current_name: str = "") -> list[str]:
    result: list[str] = []
    for candidate in re.split(r"[\n,，、;；]+", value):
        candidate = candidate.strip()
        if candidate and candidate != current_name and candidate not in result:
            result.append(candidate)
    return result


class ExerciseEntryPopup(Popup):
    """Bottom-sheet form for adding or saving a reusable single-exercise template."""

    def __init__(
        self,
        on_add: Callable[[dict[str, Any], str], bool],
        on_save_template: Callable[[dict[str, Any], str], bool],
    ):
        self.on_add = on_add
        self.on_save_template = on_save_template
        self.selected_part = "胸"
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(14))
        scroll = ScrollView(do_scroll_x=False)
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(make_label("动作名称", 14, MUTED, 26, True))
        self.name_input = make_input("例如：杠铃卧推")
        form.add_widget(self.name_input)
        form.add_widget(make_label("训练部位（单选）", 14, MUTED, 26, True))
        part_grid = GridLayout(
            cols=3,
            spacing=dp(6),
            size_hint_y=None,
            height=dp(144),
            row_default_height=dp(44),
            row_force_default=True,
        )
        self.part_buttons: dict[str, AppToggleButton] = {}
        for part in PARTS:
            button = AppToggleButton(PART_NAMES.get(part, part))
            button.state = "down" if part == self.selected_part else "normal"
            button.bind(on_release=lambda _, selected=part: self.select_part(selected))
            self.part_buttons[part] = button
            part_grid.add_widget(button)
        form.add_widget(part_grid)
        form.add_widget(make_label("重量（kg） / 组数 / 每组次数", 14, MUTED, 26, True))
        measurements = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(50))
        self.weight_input = make_input("60", numeric=True)
        self.sets_input = make_input("4", "4", numeric=True)
        self.reps_input = make_input("次数", "8", numeric=True)
        for field in (self.weight_input, self.sets_input, self.reps_input):
            measurements.add_widget(field)
        form.add_widget(measurements)
        self.rest_input = make_input("默认休息时间（秒）", "90", numeric=True)
        form.add_widget(self.rest_input)
        self.alternatives_input = make_input(
            "备选动作（可选，用逗号或换行分隔）",
            multiline=True,
        )
        form.add_widget(self.alternatives_input)
        self.error_label = make_label("", 12, DANGER, 30)
        form.add_widget(self.error_label)
        scroll.add_widget(form)
        body.add_widget(scroll)

        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(50))
        actions.add_widget(make_button("确认添加", self.confirm_add, height=50))
        actions.add_widget(
            make_button("收藏为常用模板", self.save_template, height=50, tone="secondary", font_size=12)
        )
        body.add_widget(actions)
        super().__init__(
            title="添加新动作",
            content=body,
            size_hint=(0.98, 0.9),
            pos_hint={"x": 0.01, "y": 0.02},
            auto_dismiss=False,
        )
        _style_popup(self)

    def select_part(self, selected: str) -> None:
        self.selected_part = selected
        for part, button in self.part_buttons.items():
            button.state = "down" if part == selected else "normal"

    def _values(self) -> dict[str, Any] | None:
        name = self.name_input.text.strip()
        if not name:
            self.error_label.text = "请填写动作名称。"
            return None
        try:
            sets = int(self.sets_input.text)
            reps = int(self.reps_input.text)
            weight = float(self.weight_input.text or 0)
            rest_seconds = int(self.rest_input.text)
            if (
                sets <= 0
                or reps <= 0
                or rest_seconds < 0
                or rest_seconds > 3600
                or not math.isfinite(weight)
                or weight < 0
            ):
                raise ValueError
        except ValueError:
            self.error_label.text = "请检查重量、组数、次数和休息时间。"
            return None
        self.error_label.text = ""
        return {
            "name": name,
            "sets": sets,
            "reps": reps,
            "weight": weight,
            "rest_seconds": rest_seconds,
            "alternatives": parse_alternatives(
                self.alternatives_input.text,
                name,
            ),
        }

    def confirm_add(self, *_: Any) -> None:
        exercise = self._values()
        if exercise is not None and self.on_add(exercise, self.selected_part):
            self.dismiss()

    def save_template(self, *_: Any) -> None:
        exercise = self._values()
        if exercise is not None and self.on_save_template(exercise, self.selected_part):
            self.dismiss()


class SetEntryPopup(Popup):
    def __init__(
        self,
        weight: float,
        reps: int,
        on_save: Callable[[float, int], None],
    ):
        self.on_save = on_save
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        content.add_widget(make_label("修改本组训练数据", 15, MUTED, 32, True))
        row = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(50))
        self.weight_input = make_input("重量（kg）", str(weight), numeric=True)
        self.reps_input = make_input("次数", str(reps), numeric=True)
        row.add_widget(self.weight_input)
        row.add_widget(self.reps_input)
        content.add_widget(row)
        self.error_label = make_label("", 12, DANGER, 28)
        content.add_widget(self.error_label)
        buttons = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        buttons.add_widget(make_button("保存", self.save, height=48))
        buttons.add_widget(
            make_button("取消", lambda *_: self.dismiss(), height=48, tone="neutral")
        )
        content.add_widget(buttons)
        super().__init__(
            title="训练组",
            content=content,
            size_hint=(0.92, None),
            height=dp(228),
        )
        _style_popup(self)

    def save(self, *_: Any) -> None:
        try:
            weight = float(self.weight_input.text)
            reps = int(self.reps_input.text)
            if not math.isfinite(weight) or weight < 0 or reps <= 0:
                raise ValueError
        except ValueError:
            self.error_label.text = "重量须大于等于 0，次数须为正整数。"
            return
        self.dismiss()
        self.on_save(weight, reps)


class WorkoutDetailsPopup(Popup):
    def __init__(
        self,
        title: str,
        notes: str,
        on_save: Callable[[str, str], bool],
    ):
        self.on_save = on_save
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        content.add_widget(make_label("训练名称", 14, MUTED, 26, True))
        self.title_input = make_input("例如：周一上肢训练", title)
        content.add_widget(self.title_input)
        content.add_widget(make_label("训练备注（最多 1000 字）", 14, MUTED, 26, True))
        self.notes_input = make_input("记录状态、感受或训练目标", notes, multiline=True)
        content.add_widget(self.notes_input)
        self.error_label = make_label("", 12, DANGER, 30)
        content.add_widget(self.error_label)
        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        actions.add_widget(make_button("保存", self.save, height=48))
        actions.add_widget(
            make_button("取消", lambda *_: self.dismiss(), height=48, tone="neutral")
        )
        content.add_widget(actions)
        super().__init__(
            title="训练详情",
            content=content,
            size_hint=(0.94, None),
            height=dp(390),
        )
        _style_popup(self)

    def save(self, *_: Any) -> None:
        title = self.title_input.text.strip()
        notes = self.notes_input.text.strip()
        if not title:
            self.error_label.text = "训练名称不能为空。"
            return
        if len(title) > 80 or len(notes) > 1000:
            self.error_label.text = "训练名称最多 80 字，备注最多 1000 字。"
            return
        if self.on_save(title, notes):
            self.dismiss()


PARTS = ("胸", "背", "肩", "手臂", "腿", "臀", "核心", "有氧", "全身")
PART_NAMES = {
    "胸": "胸部",
    "背": "背部",
    "肩": "肩部",
    "手臂": "手臂",
    "腿": "腿部",
    "臀": "臀部",
    "核心": "核心",
    "有氧": "有氧",
    "全身": "全身",
}


class AlternativePickerPopup(Popup):
    def __init__(
        self,
        alternatives: list[str],
        on_select: Callable[[str], None],
    ):
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        scroll = ScrollView(do_scroll_x=False)
        choices = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        choices.bind(minimum_height=choices.setter("height"))
        for alternative in alternatives:
            choices.add_widget(
                make_button(
                    alternative,
                    lambda _, name=alternative: self._select(name, on_select),
                    height=48,
                    tone="secondary",
                )
            )
        scroll.add_widget(choices)
        content.add_widget(scroll)
        cancel = make_button("取消", lambda *_: self.dismiss(), height=46, tone="neutral")
        content.add_widget(cancel)
        height = min(dp(520), dp(92 + 56 * max(1, len(alternatives))))
        super().__init__(
            title="选择替换动作",
            content=content,
            size_hint=(0.9, None),
            height=height,
        )
        _style_popup(self)

    def _select(self, alternative: str, on_select: Callable[[str], None]) -> None:
        self.dismiss()
        on_select(alternative)


class AlternativeEditorPopup(Popup):
    def __init__(
        self,
        exercise_name: str,
        alternatives: list[str],
        on_save: Callable[[list[str]], None],
    ):
        self.exercise_name = exercise_name
        self.alternatives = list(alternatives)
        self.on_save = on_save
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        existing = "已有备选：" + "、".join(alternatives) if alternatives else "当前还没有备选动作。"
        content.add_widget(make_label(existing, 13, MUTED, 42))
        content.add_widget(
            make_label("可输入一个或多个动作名称，用逗号、顿号或换行分隔。", 13, MUTED, 38)
        )
        self.input = make_input("输入备选动作", multiline=True)
        content.add_widget(self.input)
        self.error_label = make_label("", 12, DANGER, 28)
        content.add_widget(self.error_label)
        buttons = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(46))
        buttons.add_widget(make_button("添加", self.save, height=46))
        buttons.add_widget(make_button("取消", lambda *_: self.dismiss(), height=46, tone="neutral"))
        content.add_widget(buttons)
        super().__init__(
            title="添加备选动作",
            content=content,
            size_hint=(0.94, None),
            height=dp(310),
        )
        _style_popup(self)

    def save(self, *_: Any) -> None:
        candidates = parse_alternatives(self.input.text, self.exercise_name)
        new_alternatives = [
            item for item in candidates if item not in self.alternatives
        ]
        if not new_alternatives:
            self.error_label.text = "请至少输入一个新的备选动作。"
            return
        self.dismiss()
        self.on_save([*self.alternatives, *new_alternatives])


class ConfirmActionPopup(Popup):
    def __init__(
        self,
        title: str,
        message: str,
        confirm_label: str,
        on_confirm: Callable[[], None],
        *,
        confirm_tone: str = "danger",
    ):
        self.on_confirm = on_confirm
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        content.add_widget(make_label(message, 13, MUTED, 56))
        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        actions.add_widget(
            make_button("取消", lambda *_: self.dismiss(), height=48, tone="neutral")
        )
        actions.add_widget(
            make_button(confirm_label, self.confirm, height=48, tone=confirm_tone)
        )
        content.add_widget(actions)
        super().__init__(
            title=title,
            content=content,
            size_hint=(0.9, None),
            height=dp(176),
            auto_dismiss=False,
        )
        _style_popup(self)

    def confirm(self, *_: Any) -> None:
        self.dismiss()
        self.on_confirm()


class ExerciseEditorPopup(Popup):
    def __init__(
        self,
        exercise: dict[str, Any],
        on_save: Callable[[dict[str, Any]], None],
        on_delete: Callable[[], None] | None = None,
    ):
        self.exercise = dict(exercise)
        self.on_save = on_save
        self.on_delete = on_delete
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        content.add_widget(make_label("可修改动作名称、训练量、组间休息和多个备选动作。", 13, MUTED, 38))

        self.name_input = make_input("动作名称", self.exercise["name"])
        content.add_widget(self.name_input)

        number_row = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(50))
        self.sets_input = make_input("组数", str(self.exercise["sets"]), numeric=True)
        self.reps_input = make_input("每组次数", str(self.exercise["reps"]), numeric=True)
        self.weight_input = make_input("重量 kg", str(self.exercise["weight"]), numeric=True)
        for field in (self.sets_input, self.reps_input, self.weight_input):
            number_row.add_widget(field)
        content.add_widget(number_row)
        self.rest_input = make_input(
            "每组休息秒数",
            str(self.exercise.get("rest_seconds", 60)),
            numeric=True,
        )
        content.add_widget(self.rest_input)

        alternatives = self.exercise.get("alternatives", [])
        self.alternatives_input = make_input(
            "备选动作：用逗号、顿号或换行分隔",
            "、".join(alternatives),
            multiline=True,
        )
        self.alternatives_input.bind(text=self._sync_picker)
        self.name_input.bind(text=self._sync_picker)
        content.add_widget(self.alternatives_input)
        self.pick_button = make_button(
            "从备选动作中替换",
            self.open_picker,
            height=44,
            tone="secondary",
        )
        self.pick_button.disabled = not alternatives
        content.add_widget(self.pick_button)
        self.error_label = make_label("", 12, DANGER, 28)
        content.add_widget(self.error_label)

        actions = GridLayout(
            cols=3 if on_delete is not None else 2,
            spacing=dp(8),
            size_hint_y=None,
            height=dp(46),
        )
        actions.add_widget(make_button("保存修改", self.save, height=46))
        actions.add_widget(make_button("取消", lambda *_: self.dismiss(), height=46, tone="neutral"))
        if on_delete is not None:
            actions.add_widget(
                make_button("移除动作", self.delete, height=46, tone="danger")
            )
        content.add_widget(actions)
        super().__init__(
            title="编辑训练动作",
            content=content,
            size_hint=(0.96, 0.9),
        )
        _style_popup(self)

    def _sync_picker(self, *_: Any) -> None:
        self.pick_button.disabled = not parse_alternatives(
            self.alternatives_input.text,
            self.name_input.text.strip(),
        )

    def open_picker(self, *_: Any) -> None:
        alternatives = parse_alternatives(
            self.alternatives_input.text,
            self.name_input.text.strip(),
        )
        if not alternatives:
            return
        picker = AlternativePickerPopup(alternatives, self._select_alternative)
        picker.open()

    def _select_alternative(self, name: str) -> None:
        self.name_input.text = name
        current_alternatives = parse_alternatives(self.alternatives_input.text, name)
        self.alternatives_input.text = "、".join(current_alternatives)
        self.pick_button.disabled = not current_alternatives

    def save(self, *_: Any) -> None:
        name = self.name_input.text.strip()
        if not name:
            self.error_label.text = "动作名称不能为空。"
            return
        try:
            sets = int(self.sets_input.text)
            reps = int(self.reps_input.text)
            weight = float(self.weight_input.text)
            rest_seconds = int(self.rest_input.text)
            if (
                sets <= 0
                or reps <= 0
                or rest_seconds < 0
                or rest_seconds > 3600
                or not math.isfinite(weight)
                or weight < 0
            ):
                raise ValueError
        except ValueError:
            self.error_label.text = "请检查组数、次数、重量和休息秒数。"
            return
        alternatives = parse_alternatives(self.alternatives_input.text, name)
        original_name = self.exercise["name"]
        if name != original_name and original_name not in alternatives:
            alternatives.append(original_name)
        updated = {
            **self.exercise,
            "name": name,
            "sets": sets,
            "reps": reps,
            "weight": weight,
            "rest_seconds": rest_seconds,
            "alternatives": alternatives,
        }
        previous_set_count = len(self.exercise.get("set_log", []))
        if sets < previous_set_count:
            ConfirmActionPopup(
                "确认减少组数",
                f"减少组数将移除最后 {previous_set_count - sets} 组及其训练数据，无法撤销。",
                "确认调整",
                lambda: self._submit_update(updated),
            ).open()
            return
        self._submit_update(updated)

    def _submit_update(self, updated: dict[str, Any]) -> None:
        self.dismiss()
        self.on_save(updated)

    def delete(self, *_: Any) -> None:
        if self.on_delete is None:
            return
        ConfirmActionPopup(
            "确认移除动作",
            "移除后，此动作及其训练组记录将从本次训练中删除。",
            "确认移除",
            self._confirm_delete,
        ).open()

    def _confirm_delete(self) -> None:
        if self.on_delete is None:
            return
        self.dismiss()
        self.on_delete()


