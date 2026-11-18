"""Kivy cross-platform fitness logging app."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line
from kivy.metrics import dp
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

from fitness_data import FitnessStore


INK = (0.12, 0.14, 0.15, 1)
MUTED = (0.42, 0.46, 0.47, 1)
ACCENT = (0.92, 0.36, 0.20, 1)
PAPER = (0.96, 0.95, 0.91, 1)
WHITE = (1, 1, 1, 1)
PARTS = ("胸", "背", "肩", "手臂", "腿", "臀", "核心", "有氧", "全身")
FONT_NAME = "Roboto"


def register_cjk_font() -> None:
    global FONT_NAME
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path("/system/fonts/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    )
    for candidate in candidates:
        if candidate.exists():
            LabelBase.register(name="FitnessCJK", fn_regular=str(candidate))
            FONT_NAME = "FitnessCJK"
            return


def make_label(
    text: str,
    size: int = 16,
    color: tuple[float, float, float, float] = INK,
    height: int | None = None,
    bold: bool = False,
) -> Label:
    label = Label(
        text=text,
        font_name=FONT_NAME,
        font_size=dp(size),
        color=color,
        bold=bold,
        size_hint_y=None,
        height=dp(height or size * 2),
        halign="left",
        valign="middle",
        text_size=(None, None),
    )
    label.bind(width=lambda instance, width: setattr(instance, "text_size", (width, None)))
    return label


def make_button(
    text: str,
    callback: Any,
    *,
    height: int = 48,
    background: tuple[float, float, float, float] = INK,
) -> Button:
    button = Button(
        text=text,
        font_name=FONT_NAME,
        font_size=dp(15),
        size_hint_y=None,
        height=dp(height),
        background_normal="",
        background_down="",
        background_color=background,
        color=WHITE,
    )
    button.bind(on_release=callback)
    return button


def make_input(hint: str, text: str = "", *, numeric: bool = False, multiline: bool = False) -> TextInput:
    return TextInput(
        hint_text=hint,
        text=text,
        font_name=FONT_NAME,
        font_size=dp(15),
        multiline=multiline,
        input_filter="float" if numeric else None,
        size_hint_y=None,
        height=dp(84 if multiline else 48),
        padding=(dp(12), dp(12)),
        background_normal="",
        background_active="",
        background_color=WHITE,
        foreground_color=INK,
        cursor_color=ACCENT,
    )


def make_scroll_content() -> tuple[ScrollView, GridLayout]:
    scroll = ScrollView(do_scroll_x=False)
    content = GridLayout(cols=1, spacing=dp(10), padding=(dp(16), dp(16)), size_hint_y=None)
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)
    return scroll, content


class TrendChart(Widget):
    points = ListProperty([])

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.bind(points=self.redraw, size=self.redraw, pos=self.redraw)

    def redraw(self, *_: Any) -> None:
        self.canvas.clear()
        values = [float(point[1]) for point in self.points]
        if not values or self.width < dp(30) or self.height < dp(30):
            return
        left, right = self.x + dp(12), self.right - dp(12)
        bottom, top = self.y + dp(14), self.top - dp(14)
        low, high = min(values), max(values)
        if low == high:
            low -= 1
            high += 1
        coords = []
        for index, value in enumerate(values):
            x = left if len(values) == 1 else left + (right - left) * index / (len(values) - 1)
            y = bottom + (top - bottom) * (value - low) / (high - low)
            coords.extend((x, y))
        with self.canvas:
            Color(0.82, 0.84, 0.82, 1)
            Line(points=(left, bottom, right, bottom), width=1)
            if len(values) > 1:
                Color(*ACCENT)
                Line(points=coords, width=dp(2.2))
            for x, y in zip(coords[::2], coords[1::2]):
                Color(*ACCENT)
                Ellipse(pos=(x - dp(4), y - dp(4)), size=(dp(8), dp(8)))


class FitnessScreen(Screen):
    def __init__(self, app: "FitnessRecordApp", **kwargs: Any):
        super().__init__(**kwargs)
        self.app_ref = app

    @property
    def store(self) -> FitnessStore:
        return self.app_ref.store

    def notify(self, message: str) -> None:
        body = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
        body.add_widget(make_label(message, height=60))
        popup = Popup(
            title="提示",
            content=body,
            size_hint=(0.86, None),
            height=dp(150),
            title_font=FONT_NAME,
        )
        body.add_widget(make_button("知道了", lambda *_: popup.dismiss(), height=42, background=ACCENT))
        popup.open()

class WorkoutScreen(FitnessScreen):
    def __init__(self, app: "FitnessRecordApp", **kwargs: Any):
        super().__init__(app, **kwargs)
        self.draft_exercises: list[dict[str, Any]] = []
        scroll, self.content = make_scroll_content()
        self.add_widget(scroll)

        self.content.add_widget(make_label("记录一场训练", 24, bold=True))
        self.date_input = make_input("训练日期 YYYY-MM-DD", date.today().isoformat())
        self.title_input = make_input("训练名称，例如：上肢力量")
        self.content.add_widget(self.date_input)
        self.content.add_widget(self.title_input)
        self.content.add_widget(make_label("选择训练部位", 16, MUTED, 32, True))
        self.part_buttons: dict[str, ToggleButton] = {}
        part_grid = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(3 * 42 + 16))
        for part in PARTS:
            button = ToggleButton(
                text=part,
                font_name=FONT_NAME,
                font_size=dp(14),
                size_hint_y=None,
                height=dp(42),
                group=None,
                background_normal="",
                background_down="",
                background_color=(0.90, 0.90, 0.87, 1),
                color=INK,
            )
            button.bind(state=self._part_state)
            self.part_buttons[part] = button
            part_grid.add_widget(button)
        self.content.add_widget(part_grid)

        self.content.add_widget(make_label("添加动作", 16, MUTED, 32, True))
        self.exercise_name = make_input("动作名称，例如：杠铃卧推")
        self.sets_input = make_input("组数", numeric=True)
        self.reps_input = make_input("每组次数", numeric=True)
        self.exercise_weight = make_input("重量（kg）", numeric=True)
        self.content.add_widget(self.exercise_name)
        numbers = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(48))
        for item in (self.sets_input, self.reps_input, self.exercise_weight):
            numbers.add_widget(item)
        self.content.add_widget(numbers)
        self.content.add_widget(make_button("＋ 添加到本次训练", self.add_exercise, background=ACCENT))
        self.exercise_list = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        self.exercise_list.bind(minimum_height=self.exercise_list.setter("height"))
        self.content.add_widget(self.exercise_list)
        self.notes_input = make_input("训练备注（可选）", multiline=True)
        self.content.add_widget(self.notes_input)
        self.content.add_widget(make_button("保存训练记录", self.save_workout, height=52, background=ACCENT))
        self.content.add_widget(make_button("保存为训练计划", self.save_plan, background=(0.25, 0.43, 0.37, 1)))

    def _part_state(self, button: ToggleButton, state: str) -> None:
        button.background_color = ACCENT if state == "down" else (0.90, 0.90, 0.87, 1)
        button.color = WHITE if state == "down" else INK

    def selected_parts(self) -> list[str]:
        return [part for part, button in self.part_buttons.items() if button.state == "down"]

    def add_exercise(self, *_: Any) -> None:
        try:
            item = {
                "name": self.exercise_name.text.strip(),
                "sets": int(self.sets_input.text),
                "reps": int(self.reps_input.text),
                "weight": float(self.exercise_weight.text or 0),
            }
            if not item["name"] or item["sets"] <= 0 or item["reps"] <= 0 or item["weight"] < 0:
                raise ValueError
        except ValueError:
            self.notify("请填写动作名称、正数组数和次数，以及不小于 0 的重量。")
            return
        self.draft_exercises.append(item)
        self.exercise_name.text = ""
        self.sets_input.text = ""
        self.reps_input.text = ""
        self.exercise_weight.text = ""
        self.render_exercises()

    def render_exercises(self) -> None:
        self.exercise_list.clear_widgets()
        for index, item in enumerate(self.draft_exercises):
            row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            row.add_widget(
                make_label(
                    f"{item['name']}  ·  {item['sets']} 组 × {item['reps']} 次  ·  {item['weight']:g} kg",
                    14,
                    height=42,
                )
            )
            row.add_widget(make_button("移除", lambda _, i=index: self.remove_exercise(i), height=38, background=(0.55, 0.25, 0.20, 1)))
            self.exercise_list.add_widget(row)

    def remove_exercise(self, index: int) -> None:
        if 0 <= index < len(self.draft_exercises):
            self.draft_exercises.pop(index)
            self.render_exercises()

    def save_workout(self, *_: Any) -> None:
        try:
            self.store.add_workout(
                self.date_input.text.strip(),
                self.title_input.text,
                self.selected_parts(),
                self.draft_exercises,
                self.notes_input.text,
            )
        except ValueError as error:
            self.notify(str(error))
            return
        self.reset_form()
        self.notify("训练记录已保存到本机。")

    def save_plan(self, *_: Any) -> None:
        try:
            self.store.add_plan(self.title_input.text, self.selected_parts(), self.draft_exercises)
        except ValueError as error:
            self.notify(str(error))
            return
        self.notify("训练计划已保存，可在“计划”页重复使用。")

    def load_plan(self, plan: dict[str, Any]) -> None:
        self.title_input.text = plan["title"]
        self.date_input.text = date.today().isoformat()
        for part, button in self.part_buttons.items():
            button.state = "down" if part in plan["body_parts"] else "normal"
        self.draft_exercises = [dict(item) for item in plan["exercises"]]
        self.notes_input.text = ""
        self.render_exercises()
        self.app_ref.manager.current = "workout"

    def reset_form(self) -> None:
        self.date_input.text = date.today().isoformat()
        self.title_input.text = ""
        self.notes_input.text = ""
        for button in self.part_buttons.values():
            button.state = "normal"
        self.draft_exercises = []
        self.render_exercises()


class PlansScreen(FitnessScreen):
    def __init__(self, app: "FitnessRecordApp", **kwargs: Any):
        super().__init__(app, **kwargs)
        scroll, self.content = make_scroll_content()
        self.add_widget(scroll)

    def on_pre_enter(self, *_: Any) -> None:
        self.content.clear_widgets()
        self.content.add_widget(make_label("我的训练计划", 24, bold=True))
        if not self.store.data["plans"]:
            self.content.add_widget(make_label("还没有计划。先在“训练”页设置动作，再点“保存为训练计划”。", 15, MUTED, 68))
            return
        for plan in reversed(self.store.data["plans"]):
            card = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(195), spacing=dp(6), padding=dp(12))
            card.add_widget(make_label(plan["title"], 18, bold=True))
            card.add_widget(make_label("部位：" + "、".join(plan["body_parts"]), 14, MUTED))
            description = "；".join(
                f"{item['name']} {item['sets']}组×{item['reps']}次 {item['weight']:g}kg"
                for item in plan["exercises"]
            )
            card.add_widget(make_label(description, 13, MUTED, 42))
            actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            actions.add_widget(make_button("按此计划训练", lambda _, p=plan: self.app_ref.workout_screen.load_plan(p), height=42, background=ACCENT))
            actions.add_widget(make_button("删除", lambda _, p=plan: self.delete_plan(p["id"]), height=42, background=(0.55, 0.25, 0.20, 1)))
            card.add_widget(actions)
            self.content.add_widget(card)

    def delete_plan(self, plan_id: str) -> None:
        self.store.delete("plans", plan_id)
        self.on_pre_enter()


class RecordsScreen(FitnessScreen):
    def __init__(self, app: "FitnessRecordApp", **kwargs: Any):
        super().__init__(app, **kwargs)
        scroll, self.content = make_scroll_content()
        self.add_widget(scroll)

    def on_pre_enter(self, *_: Any) -> None:
        self.content.clear_widgets()
        self.content.add_widget(make_label("训练历史", 24, bold=True))
        records = self.store.recent_workouts()
        if not records:
            self.content.add_widget(make_label("保存训练后，记录会显示在这里。", 15, MUTED))
            return
        for workout in records:
            card = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4), padding=dp(10))
            card.add_widget(make_label(f"{workout['date']}  ·  {workout['title']}", 16, bold=True))
            card.add_widget(make_label("部位：" + "、".join(workout["body_parts"]), 13, MUTED))
            details = "；".join(
                f"{item['name']} {item['sets']}组×{item['reps']}次 {item['weight']:g}kg"
                for item in workout["exercises"]
            )
            detail_height = max(40, min(80, 20 * (len(details) // 34 + 1)))
            card.add_widget(make_label(details, 13, MUTED, detail_height))
            if workout.get("notes"):
                card.add_widget(make_label("备注：" + workout["notes"], 13, MUTED, 32))
            card.height = dp(130 + detail_height + (36 if workout.get("notes") else 0))
            card.add_widget(make_button("删除记录", lambda _, w=workout: self.delete_workout(w["id"]), height=38, background=(0.55, 0.25, 0.20, 1)))
            self.content.add_widget(card)

    def delete_workout(self, workout_id: str) -> None:
        self.store.delete("workouts", workout_id)
        self.on_pre_enter()


class BodyWeightScreen(FitnessScreen):
    def __init__(self, app: "FitnessRecordApp", **kwargs: Any):
        super().__init__(app, **kwargs)
        scroll, self.content = make_scroll_content()
        self.add_widget(scroll)
        self.content.add_widget(make_label("记录体重", 24, bold=True))
        self.date_input = make_input("记录日期 YYYY-MM-DD", date.today().isoformat())
        self.weight_input = make_input("体重（kg）", numeric=True)
        self.notes_input = make_input("备注（可选）")
        self.content.add_widget(self.date_input)
        self.content.add_widget(self.weight_input)
        self.content.add_widget(self.notes_input)
        self.content.add_widget(make_button("保存体重", self.save_weight, background=ACCENT))
        self.history = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
        self.history.bind(minimum_height=self.history.setter("height"))
        self.content.add_widget(make_label("体重历史", 17, MUTED, 38, True))
        self.content.add_widget(self.history)

    def save_weight(self, *_: Any) -> None:
        try:
            self.store.add_body_weight(self.date_input.text.strip(), self.weight_input.text, self.notes_input.text)
        except ValueError as error:
            self.notify(str(error))
            return
        self.weight_input.text = ""
        self.notes_input.text = ""
        self.on_pre_enter()
        self.notify("体重记录已保存。")

    def on_pre_enter(self, *_: Any) -> None:
        self.history.clear_widgets()
        entries = self.store.recent_body_weights()
        if not entries:
            self.history.add_widget(make_label("还没有体重记录。", 14, MUTED))
            return
        for entry in entries:
            row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            row.add_widget(make_label(f"{entry['date']}  ·  {entry['weight']:g} kg", 14, height=42))
            row.add_widget(make_button("删除", lambda _, e=entry: self.delete_weight(e["id"]), height=38, background=(0.55, 0.25, 0.20, 1)))
            self.history.add_widget(row)

    def delete_weight(self, entry_id: str) -> None:
        self.store.delete("body_weights", entry_id)
        self.on_pre_enter()


class ProgressScreen(FitnessScreen):
    def __init__(self, app: "FitnessRecordApp", **kwargs: Any):
        super().__init__(app, **kwargs)
        scroll, self.content = make_scroll_content()
        self.add_widget(scroll)
        self.content.add_widget(make_label("身体变化趋势", 24, bold=True))
        self.month_label = make_label("", 16, ACCENT, 32, True)
        self.content.add_widget(self.month_label)
        self.part_label = make_label("", 15, MUTED, 70)
        self.content.add_widget(self.part_label)
        self.content.add_widget(make_label("训练总量趋势（组 × 次 × kg）", 16, MUTED, 36, True))
        self.volume_chart = TrendChart(size_hint_y=None, height=dp(150))
        self.content.add_widget(self.volume_chart)
        self.volume_caption = make_label("", 12, MUTED, 32)
        self.content.add_widget(self.volume_caption)
        self.content.add_widget(make_label("体重趋势（kg）", 16, MUTED, 36, True))
        self.weight_chart = TrendChart(size_hint_y=None, height=dp(150))
        self.content.add_widget(self.weight_chart)
        self.weight_caption = make_label("", 12, MUTED, 32)
        self.content.add_widget(self.weight_caption)

    def on_pre_enter(self, *_: Any) -> None:
        month = date.today().strftime("%Y-%m")
        summary = self.store.monthly_summary(month)
        self.month_label.text = f"{month} · 训练 {summary['sessions']} 次"
        self.part_label.text = (
            "本月部位：" + ("、".join(f"{part} {count}次" for part, count in summary["body_parts"].most_common()) or "暂无训练记录")
        )
        volume = self.store.training_volume_trend()
        self.volume_chart.points = volume
        self.volume_caption.text = "  →  ".join(f"{item[0][5:]} {item[1]:g}" for item in volume) or "记录训练后显示趋势"
        weights = self.store.body_weight_trend()
        self.weight_chart.points = weights
        self.weight_caption.text = "  →  ".join(f"{item[0][5:]} {item[1]:g}" for item in weights) or "记录体重后显示趋势"


class FitnessRecordApp(App):
    title = "健身记录"

    def build(self) -> BoxLayout:
        register_cjk_font()
        self.store = FitnessStore(Path(self.user_data_dir) / "fitness_record.json")
        root = BoxLayout(orientation="vertical", spacing=dp(6), padding=(dp(10), dp(8)))
        Window.clearcolor = PAPER
        header = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(60))
        header.add_widget(make_label("FITNESS RECORD", 12, ACCENT, 22, True))
        header.add_widget(make_label("健身记录", 23, bold=True))
        root.add_widget(header)

        self.manager = ScreenManager()
        self.workout_screen = WorkoutScreen(self, name="workout")
        self.manager.add_widget(self.workout_screen)
        self.manager.add_widget(PlansScreen(self, name="plans"))
        self.manager.add_widget(RecordsScreen(self, name="records"))
        self.manager.add_widget(ProgressScreen(self, name="progress"))
        self.manager.add_widget(BodyWeightScreen(self, name="weight"))
        root.add_widget(self.manager)

        navigation = GridLayout(cols=5, size_hint_y=None, height=dp(54), spacing=dp(4))
        for label, screen_name in (
            ("训练", "workout"),
            ("计划", "plans"),
            ("历史", "records"),
            ("趋势", "progress"),
            ("体重", "weight"),
        ):
            navigation.add_widget(
                make_button(
                    label,
                    lambda _, name=screen_name: setattr(self.manager, "current", name),
                    height=50,
                    background=ACCENT if screen_name == "workout" else (0.27, 0.31, 0.31, 1),
                )
            )
        root.add_widget(navigation)
        return root


if __name__ == "__main__":
    FitnessRecordApp().run()
