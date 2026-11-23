"""Adaptive workout, calendar history, and exercise library screens."""

from __future__ import annotations

import calendar
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

from kivy.metrics import dp
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.utils import platform

from fitness_data import FitnessStoreError
from fitness_ui.dialogs import (
    BackupImportPopup,
    ConfirmActionPopup,
    ExerciseEntryPopup,
    ExerciseEditorPopup,
    SetEntryPopup,
    WorkoutDetailsPopup,
)
from fitness_ui.export import ExportError, ExportPermissionRequired, export_json, share_export
from fitness_ui.theme import BORDER, MUTED, PRIMARY, SURFACE, TEXT, font_name
from fitness_ui.widgets import (
    AppToggleButton,
    FitnessScreen,
    SurfaceCard,
    make_button,
    make_input,
    make_label,
    make_scroll_content,
    section_heading,
)


LOGGER = logging.getLogger(__name__)
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


class ExerciseLogCard(SurfaceCard):
    """Compact set-by-set workout log modeled on mobile gym trackers."""

    def __init__(
        self,
        exercise: dict[str, Any],
        previous_sets: list[dict[str, Any]],
        *,
        is_record: bool,
        finished: bool,
        on_edit: Any,
        on_rest: Any,
        on_toggle_set: Any,
        on_edit_set: Any,
        on_add_set: Any,
    ):
        rows = exercise.get("set_log", [])
        completed_rows = [entry for entry in rows if entry["completed"]]
        completed_volume = sum(entry["weight"] * entry["reps"] for entry in completed_rows)
        self.exercise_name = exercise["name"]
        self.rest_seconds = exercise.get("rest_seconds", 60)
        super().__init__(
            size_hint_y=None,
            height=dp(156 + 48 * len(rows)),
            spacing=dp(3),
            padding=(dp(10), dp(6)),
        )
        title_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(4),
        )
        title_row.add_widget(make_label(exercise["name"], 15, TEXT, 44, True, shorten=True))
        if is_record:
            title_row.add_widget(make_label("PR", 11, PRIMARY, 26, True))
        options = make_button(
            "编辑",
            lambda *_: on_edit(),
            height=44,
            tone="neutral",
            font_size=11,
        )
        options.size_hint_x = None
        options.width = dp(48)
        options.disabled = finished
        title_row.add_widget(options)
        self.add_widget(title_row)

        self.add_widget(
            make_label(
                f"已完成 {len(completed_rows)}/{len(rows)} 组 · 训练量 {completed_volume:g} kg",
                10,
                MUTED,
                18,
            )
        )

        column_header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(24),
        )
        for label, width in (("组", .10), ("上次", .25), ("kg", .20), ("次", .18), ("", .27)):
            heading = make_label(label, 10, MUTED, 24, True)
            heading.size_hint_x = width
            column_header.add_widget(heading)
        self.add_widget(column_header)

        for index, entry in enumerate(rows):
            previous = previous_sets[min(index, len(previous_sets) - 1)] if previous_sets else None
            previous_text = f"{previous['weight']:g}×{previous['reps']}" if previous else "—"
            row = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(44),
                spacing=dp(2),
            )
            group_label = make_label(str(index + 1), 11, MUTED, 44, True)
            group_label.size_hint_x = .10
            row.add_widget(group_label)
            previous_label = make_label(previous_text, 10, MUTED, 44)
            previous_label.size_hint_x = .25
            row.add_widget(previous_label)
            weight_button = make_button(
                f"{entry['weight']:g}",
                lambda _, position=index: on_edit_set(position),
                height=44,
                tone="neutral",
                font_size=11,
            )
            weight_button.size_hint_x = .20
            weight_button.disabled = finished
            row.add_widget(weight_button)
            reps_button = make_button(
                str(entry["reps"]),
                lambda _, position=index: on_edit_set(position),
                height=44,
                tone="neutral",
                font_size=11,
            )
            reps_button.size_hint_x = .18
            reps_button.disabled = finished
            row.add_widget(reps_button)
            complete = bool(entry["completed"])
            check = make_button(
                "已完成" if complete else "开始计时",
                lambda _, position=index, state=complete: on_toggle_set(position, not state),
                height=44,
                tone="primary" if complete else "secondary",
                font_size=11,
                padding=(dp(2), dp(2)),
            )
            check.size_hint_x = .27
            check.disabled = finished
            row.add_widget(check)
            self.add_widget(row)

        controls = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(5),
        )
        add_set = make_button(
            "+ 添加一组",
            lambda *_: on_add_set(),
            height=44,
            tone="secondary",
            font_size=12,
        )
        add_set.size_hint_x = .5
        add_set.disabled = finished
        controls.add_widget(add_set)
        self.rest_button = make_button(
            f"休息 {self.rest_seconds} 秒",
            lambda *_: on_rest(),
            height=44,
            font_size=12,
        )
        self.rest_button.size_hint_x = .5
        self.rest_button.disabled = finished
        controls.add_widget(self.rest_button)
        self.add_widget(controls)

    def update_rest_timer(self, remaining: int | None) -> None:
        if remaining is None:
            self.rest_button.text = f"休息 {self.rest_seconds} 秒"
            return
        minutes, seconds = divmod(max(0, remaining), 60)
        self.rest_button.text = f"剩余 {minutes:02d}:{seconds:02d}"


class WorkoutScreen(FitnessScreen):
    def __init__(self, app: Any, **kwargs: Any):
        super().__init__(app, **kwargs)
        self.today = date.today().isoformat()
        self.root_layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=(dp(10), dp(8)),
        )
        self.header = SurfaceCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(58),
            spacing=dp(8),
            padding=(dp(14), dp(6)),
        )
        self.header_title = make_label("训练中", 17, TEXT, 40, True)
        self.header_status = make_label("", 13, PRIMARY, 38, True, shorten=True)
        self.header.add_widget(self.header_title)
        self.header.add_widget(self.header_status)
        self.finish_button = make_button(
            "完成",
            self.finish_workout,
            height=38,
            tone="primary",
            font_size=11,
        )
        self.finish_button.size_hint_x = None
        self.finish_button.width = dp(58)
        self.header.add_widget(self.finish_button)
        self.root_layout.add_widget(self.header)

        self.session_card = SurfaceCard(
            orientation="vertical",
            size_hint_y=None,
            height=0,
            spacing=dp(2),
            padding=(dp(12), dp(6)),
        )
        session_title_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(32),
            spacing=dp(4),
        )
        self.session_title = make_label("", 14, TEXT, 32, True, shorten=True)
        session_title_row.add_widget(self.session_title)
        self.session_edit_button = make_button(
            "详情",
            self.open_workout_details,
            height=32,
            tone="neutral",
            font_size=11,
        )
        self.session_edit_button.size_hint_x = None
        self.session_edit_button.width = dp(52)
        session_title_row.add_widget(self.session_edit_button)
        self.session_card.add_widget(session_title_row)
        self.session_duration = make_label("", 11, PRIMARY, 20, True)
        self.session_card.add_widget(self.session_duration)
        self.session_notes = make_label("", 11, MUTED, 20, shorten=True)
        self.session_card.add_widget(self.session_notes)
        self.root_layout.add_widget(self.session_card)

        self.scroll, self.content = make_scroll_content()
        self.root_layout.add_widget(self.scroll)
        self.add_action_button = make_button(
            "+ 记录新动作",
            self.open_add_action,
            height=56,
            font_size=17,
        )
        self.root_layout.add_widget(self.add_action_button)
        self.add_widget(self.root_layout)
        self.display_workout_id: str | None = None
        self.exercise_cards: list[ExerciseLogCard] = []
        Clock.schedule_interval(self._update_session_duration, 1)

    def on_pre_enter(self, *_: Any) -> None:
        self.refresh_today()

    def _today_workouts(self) -> list[dict[str, Any]]:
        return sorted(
            (item for item in self.store.data["workouts"] if item["date"] == self.today),
            key=lambda item: (item.get("training_time", ""), item["id"]),
        )

    def refresh_today(self) -> None:
        self.today = date.today().isoformat()
        workouts = self._today_workouts()
        active = self.store.active_workout(self.today)
        display_workouts = [active] if active is not None else workouts[-1:]
        session = display_workouts[0] if display_workouts else None
        self.display_workout_id = session["id"] if session is not None else None
        self.session_card.height = dp(88) if session is not None else 0
        if session is not None:
            self.session_title.text = session["title"]
            self.session_notes.text = session["notes"] or "添加训练备注，记录本次状态"
            self._update_session_duration()
        action_count = sum(len(item["exercises"]) for item in display_workouts)
        parts = list(dict.fromkeys(
            part for workout in display_workouts for part in workout["body_parts"]
        ))
        part_text = "、".join(PART_NAMES.get(part, part) for part in parts) or "未选择部位"
        completed_count = sum(
            entry["completed"]
            for workout in display_workouts
            for exercise in workout["exercises"]
            for entry in exercise.get("set_log", [])
        )
        set_count = sum(
            len(exercise.get("set_log", []))
            for workout in display_workouts
            for exercise in workout["exercises"]
        )
        self.header_title.text = "训练中" if active is not None else "今日训练"
        self.header_status.text = f"{part_text} · {completed_count}/{set_count} 组"
        self.finish_button.disabled = active is None
        self.content.clear_widgets()
        self.exercise_cards = []
        self.content.add_widget(
            section_heading(
                date.today().strftime("%Y年%m月%d日"),
                "记录每组重量、次数，完成后点勾保存"
                if active is not None
                else (f"已完成 {action_count} 个动作" if action_count else "还没有开始今天的训练"),
            )
        )

        records = {item["name"]: item for item in self.store.personal_records()}
        for workout in display_workouts:
            for index, exercise in enumerate(workout["exercises"]):
                record = records.get(exercise["name"])
                logged_weights = [
                    float(entry["weight"])
                    for entry in exercise.get("set_log", [])
                    if entry["completed"]
                ]
                is_record = record is not None and bool(logged_weights) and max(
                    logged_weights
                ) >= record["weight"]
                card = ExerciseLogCard(
                    exercise,
                    self._previous_sets(exercise["name"], workout["id"]),
                    is_record=is_record,
                    finished=bool(workout["finished"]),
                    on_edit=lambda selected=workout, position=index: self.edit_exercise(
                        selected["id"], position
                    ),
                    on_rest=lambda selected=exercise: self.start_rest_timer(selected),
                    on_toggle_set=lambda position, value, selected=workout, action_index=index: self.toggle_set(
                        selected["id"],
                        action_index,
                        position,
                        value,
                        selected["exercises"][action_index],
                    ),
                    on_edit_set=lambda position, selected=workout, action_index=index: self.edit_set(
                        selected["id"],
                        action_index,
                        position,
                        selected["exercises"][action_index],
                    ),
                    on_add_set=lambda selected=workout, position=index: self.add_set(
                        selected["id"], position
                    ),
                )
                self.content.add_widget(card)
                self.exercise_cards.append(card)

        rest_day = any(item["date"] == self.today for item in self.store.data["rest_days"])
        if not rest_day:
            self.content.add_widget(
                make_button(
                    "今天太累，休息一天",
                    self.toggle_rest_day,
                    height=44,
                    tone="neutral",
                )
            )
        else:
            self.content.add_widget(
                make_button(
                    "已标记休息日 · 点击取消",
                    self.toggle_rest_day,
                    height=44,
                    tone="neutral",
                )
            )
        if not display_workouts and not rest_day:
            self.content.add_widget(
                make_label("今天还没有训练动作，点击下方按钮开始记录。", 14, MUTED, 48)
            )
        snapshot = getattr(self.app_ref, "rest_timer_snapshot", None)
        if snapshot is not None:
            state, remaining = snapshot()
            self.update_rest_timer(state, remaining)

    def update_rest_timer(
        self,
        state: dict[str, Any] | None,
        remaining: int,
    ) -> None:
        exercise_name = (
            state.get("exercise")
            if state is not None and state.get("status") == "running"
            else None
        )
        for card in self.exercise_cards:
            card.update_rest_timer(
                remaining if card.exercise_name == exercise_name else None
            )

    @staticmethod
    def _format_duration(seconds: int) -> str:
        minutes, remainder = divmod(max(0, seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{remainder:02d}"
        return f"{minutes:02d}:{remainder:02d}"

    def _update_session_duration(self, *_: Any) -> None:
        workout_id = getattr(self, "display_workout_id", None)
        if workout_id is None:
            return
        workout = next(
            (item for item in self.store.data["workouts"] if item["id"] == workout_id),
            None,
        )
        if workout is None:
            self.session_duration.text = "训练时长 —"
            return
        started_at = workout.get("started_at")
        if not workout["finished"] and isinstance(started_at, (int, float)):
            seconds = int(max(0, time.time() - started_at))
        else:
            seconds = workout.get("duration_seconds")
        self.session_duration.text = (
            f"训练时长 {self._format_duration(seconds)}"
            if isinstance(seconds, int)
            else "训练时长未记录"
        )

    def open_workout_details(self, *_: Any) -> None:
        workout_id = self.display_workout_id
        if workout_id is None:
            self.notify("今天还没有训练记录。")
            return
        workout = next(
            (
                item for item in self.store.data["workouts"]
                if item["id"] == workout_id
            ),
            None,
        )
        if workout is None:
            self.notify("找不到这次训练记录。")
            return
        WorkoutDetailsPopup(
            workout["title"],
            workout["notes"],
            lambda title, notes: self._save_workout_details(workout_id, title, notes),
        ).open()

    def _save_workout_details(self, workout_id: str, title: str, notes: str) -> bool:
        try:
            self.store.update_workout_details(workout_id, title, notes)
        except (KeyError, ValueError, FitnessStoreError) as error:
            LOGGER.exception("Unable to update workout details")
            self.notify(f"保存训练详情失败：{error}")
            return False
        self.refresh_today()
        return True

    def _previous_sets(
        self,
        exercise_name: str,
        exclude_workout_id: str,
    ) -> list[dict[str, Any]]:
        for workout in self.store.recent_workouts():
            if workout["id"] == exclude_workout_id:
                continue
            for exercise in workout["exercises"]:
                if exercise["name"] == exercise_name:
                    entries = exercise.get("set_log", [])
                    if entries:
                        return entries
                    return [
                        {
                            "weight": exercise["weight"],
                            "reps": exercise["reps"],
                        }
                        for _ in range(exercise["sets"])
                    ]
        return []

    def open_add_action(self, *_: Any) -> None:
        ExerciseEntryPopup(
            on_add=self._add_action,
            on_save_template=self._save_action_template,
        ).open()

    def _add_action(self, exercise: dict[str, Any], body_part: str) -> bool:
        try:
            self.store.add_daily_exercise(self.today, body_part, exercise)
        except ValueError as error:
            self.notify(str(error))
            return False
        except FitnessStoreError as error:
            LOGGER.exception("Unable to save today's exercise")
            self.notify(f"添加动作失败：{error}")
            return False
        self.refresh_today()
        return True

    def _save_action_template(self, exercise: dict[str, Any], body_part: str) -> bool:
        try:
            self.store.add_plan(f"{exercise['name']} 模板", [body_part], [exercise])
        except ValueError as error:
            self.notify(str(error))
            return False
        except FitnessStoreError as error:
            LOGGER.exception("Unable to save exercise template")
            self.notify(f"保存动作模板失败：{error}")
            return False
        self.notify("动作模板已保存到资料库。")
        return True

    def toggle_rest_day(self, *_: Any) -> None:
        is_rest_day = not any(
            item["date"] == self.today for item in self.store.data["rest_days"]
        )
        try:
            self.store.set_rest_day(self.today, is_rest_day)
        except ValueError as error:
            self.notify(str(error))
            return
        except FitnessStoreError as error:
            LOGGER.exception("Unable to update today's rest-day status")
            self.notify(f"更新休息日失败：{error}")
            return
        self.refresh_today()

    def edit_exercise(self, workout_id: str, index: int) -> None:
        workout = next(
            (item for item in self.store.data["workouts"] if item["id"] == workout_id),
            None,
        )
        if workout is None or not 0 <= index < len(workout["exercises"]):
            self.notify("找不到要编辑的训练动作。")
            return

        def save(updated: dict[str, Any]) -> None:
            try:
                self.store.replace_workout_exercise(workout_id, index, updated)
            except (KeyError, ValueError, FitnessStoreError) as error:
                LOGGER.exception("Unable to update today's exercise")
                self.notify(f"更新动作失败：{error}")
                return
            self.refresh_today()

        ExerciseEditorPopup(
            workout["exercises"][index],
            save,
            lambda: self.remove_exercise(workout_id, index),
            deleting_last_exercise=len(workout["exercises"]) == 1,
        ).open()

    def remove_exercise(self, workout_id: str, index: int) -> None:
        try:
            self.store.remove_workout_exercise(workout_id, index)
        except (KeyError, FitnessStoreError) as error:
            LOGGER.exception("Unable to remove today's exercise")
            self.notify(f"删除动作失败：{error}")
            return
        self.refresh_today()

    def start_rest_timer(self, exercise: dict[str, Any]) -> None:
        controller = self.app_ref.timer_controller
        state = controller.state
        if state is not None and state.get("status") == "running":
            if state.get("exercise") != exercise["name"]:
                self.notify(f"{state.get('exercise', '当前动作')}的休息计时仍在运行。")
            self.app_ref.open_rest_timer()
            return
        try:
            controller.start(
                exercise["name"],
                exercise.get("rest_seconds", 60),
            )
        except ValueError as error:
            self.notify(str(error))
            return
        self.app_ref.open_rest_timer()

    def finish_workout(self, *_: Any) -> None:
        workout = self.store.active_workout(self.today)
        if workout is None:
            self.notify("当前没有进行中的训练。")
            return
        incomplete_sets = sum(
            not entry["completed"]
            for exercise in workout["exercises"]
            for entry in exercise.get("set_log", [])
        )
        if incomplete_sets:
            title = "仍有训练组未完成"
            message = f"还有 {incomplete_sets} 组未完成。仍要结束并保存本次训练吗？"
            confirm_label = "仍要结束"
            confirm_tone = "danger"
        else:
            title = "结束训练"
            message = "所有训练组均已完成，确定结束并保存本次训练吗？"
            confirm_label = "结束训练"
            confirm_tone = "primary"
        ConfirmActionPopup(
            title,
            message,
            confirm_label,
            self._finish_workout_confirmed,
            confirm_tone=confirm_tone,
        ).open()

    def _finish_workout_confirmed(self) -> None:
        try:
            workout = self.store.finish_workout(self.today)
        except FitnessStoreError as error:
            LOGGER.exception("Unable to finish today's workout")
            self.notify(f"结束训练失败：{error}")
            return
        if workout is None:
            self.notify("当前没有进行中的训练。")
            return
        self.refresh_today()
        self.notify("训练已完成并保存。")

    def toggle_set(
        self,
        workout_id: str,
        exercise_index: int,
        set_index: int,
        completed: bool,
        exercise: dict[str, Any],
    ) -> None:
        try:
            self.store.update_workout_set(
                workout_id,
                exercise_index,
                set_index,
                completed=completed,
            )
        except (KeyError, ValueError, FitnessStoreError) as error:
            LOGGER.exception("Unable to update workout set")
            self.notify(f"更新训练组失败：{error}")
            return
        self.refresh_today()
        if completed and exercise.get("rest_seconds", 0) > 0:
            self.start_rest_timer(exercise)
        elif not completed:
            controller = getattr(self.app_ref, "timer_controller", None)
            state = getattr(controller, "state", None)
            if (
                controller is not None
                and state is not None
                and state.get("status") == "running"
                and state.get("exercise") == exercise["name"]
            ):
                try:
                    controller.cancel()
                except ValueError as error:
                    LOGGER.exception("Unable to cancel rest timer after undoing a set")
                    self.notify(f"已撤销训练组，但取消计时失败：{error}")

    def edit_set(
        self,
        workout_id: str,
        exercise_index: int,
        set_index: int,
        exercise: dict[str, Any],
    ) -> None:
        entries = exercise.get("set_log", [])
        if not 0 <= set_index < len(entries):
            return

        def save(weight: float, reps: int) -> None:
            try:
                self.store.update_workout_set(
                    workout_id,
                    exercise_index,
                    set_index,
                    weight=weight,
                    reps=reps,
                )
            except (KeyError, ValueError, FitnessStoreError) as error:
                LOGGER.exception("Unable to edit workout set")
                self.notify(f"修改训练组失败：{error}")
                return
            self.refresh_today()

        SetEntryPopup(
            float(entries[set_index]["weight"]),
            int(entries[set_index]["reps"]),
            save,
        ).open()

    def add_set(self, workout_id: str, exercise_index: int) -> None:
        try:
            self.store.add_workout_set(workout_id, exercise_index)
        except (KeyError, ValueError, FitnessStoreError) as error:
            LOGGER.exception("Unable to add workout set")
            self.notify(f"添加训练组失败：{error}")
            return
        self.refresh_today()


class CalendarHistoryScreen(FitnessScreen):
    def __init__(self, app: Any, **kwargs: Any):
        super().__init__(app, **kwargs)
        today = date.today()
        self.month = today.replace(day=1)
        self.selected_date = today.isoformat()
        self._pending_restore_document: dict[str, Any] | None = None
        self.root_layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=(dp(10), dp(8)),
        )
        self.scroll, self.content = make_scroll_content()
        self.root_layout.add_widget(self.scroll)
        self.add_widget(self.root_layout)

    def on_pre_enter(self, *_: Any) -> None:
        self.render()

    def move_month(self, offset: int) -> None:
        month_index = self.month.year * 12 + self.month.month - 1 + offset
        self.month = date(month_index // 12, month_index % 12 + 1, 1)
        self.selected_date = self.month.isoformat()
        self.render()

    def select_day(self, day: int) -> None:
        self.selected_date = date(self.month.year, self.month.month, day).isoformat()
        self.render()

    def export_data(self, *_: Any) -> None:
        try:
            destination = export_json(self.store.data, self.app_ref.user_data_dir)
        except ExportPermissionRequired:
            self._request_export_permission()
            return
        except ExportError as error:
            LOGGER.exception("Unable to export fitness data")
            self.notify(f"导出失败：{error}")
            return
        if platform == "ios":
            try:
                if not isinstance(destination, Path):
                    raise ExportError("导出文件位置无效。")
                share_export(destination)
            except ExportError as error:
                LOGGER.exception("Unable to share exported fitness data")
                self.notify(f"导出失败：{error}")
                return
            self.notify("已打开系统分享菜单，可选择“存储到文件”保存备份。")
        elif platform == "android":
            self.notify("已导出到系统“下载”目录的 FitnessRecord 文件夹。")
        else:
            self.notify(f"数据已导出到：\n{destination}")

    def _request_export_permission(self) -> None:
        try:
            from android.permissions import Permission, request_permissions
        except ImportError as error:
            LOGGER.exception("Android storage permission API is unavailable")
            self._pending_restore_document = None
            self.notify(f"无法请求下载目录权限：{error}")
            return
        request_permissions(
            [Permission.WRITE_EXTERNAL_STORAGE],
            self._on_export_permission_result,
        )

    def _on_export_permission_result(
        self,
        _permissions: list[str],
        grants: list[bool],
    ) -> None:
        if not grants or not all(grants):
            pending_restore = self._pending_restore_document
            self._pending_restore_document = None
            if pending_restore is not None:
                self.notify("未获得存储权限，未恢复备份。")
            else:
                self.notify("未获得存储权限，数据未导出。")
            return
        pending_restore = self._pending_restore_document
        if pending_restore is not None:
            self._pending_restore_document = None
            self._restore_backup(pending_restore)
            return
        self.export_data()

    def render(self) -> None:
        self.content.clear_widgets()
        title_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )
        title_row.add_widget(make_label("训练日历", 20, TEXT, 42, True))
        backfill_button = make_button(
            "补录",
            self.open_backfill,
            height=42,
            tone="secondary",
            font_size=11,
        )
        backfill_button.size_hint_x = None
        backfill_button.width = dp(52)
        backfill_button.disabled = self.selected_date >= date.today().isoformat()
        title_row.add_widget(backfill_button)
        restore_button = make_button(
            "恢复",
            self.open_restore,
            height=42,
            tone="secondary",
            font_size=11,
        )
        restore_button.size_hint_x = None
        restore_button.width = dp(52)
        title_row.add_widget(restore_button)
        export_button = make_button("导出", self.export_data, height=42, tone="secondary")
        export_button.size_hint_x = None
        export_button.width = dp(56)
        export_button.font_size = dp(11)
        title_row.add_widget(export_button)
        self.content.add_widget(title_row)

        month_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(8),
        )
        previous = make_button("‹", lambda *_: self.move_month(-1), height=42, tone="secondary")
        previous.size_hint_x = None
        previous.width = dp(48)
        month_row.add_widget(previous)
        month_row.add_widget(
            make_label(f"{self.month.year} 年 {self.month.month:02d} 月", 17, TEXT, 42, True)
        )
        following = make_button("›", lambda *_: self.move_month(1), height=42, tone="secondary")
        following.size_hint_x = None
        following.width = dp(48)
        month_row.add_widget(following)
        self.content.add_widget(month_row)

        weekdays = GridLayout(cols=7, size_hint_y=None, height=dp(24))
        for label in ("一", "二", "三", "四", "五", "六", "日"):
            weekdays.add_widget(make_label(label, 12, MUTED, 24))
        self.content.add_widget(weekdays)
        calendar_grid = GridLayout(
            cols=7,
            spacing=dp(4),
            size_hint_y=None,
            row_default_height=dp(48),
            row_force_default=True,
        )
        calendar_grid.height = dp(48 * 6 + 4 * 5)
        self.content.add_widget(calendar_grid)

        month_key = self.month.strftime("%Y-%m")
        summary = self.store.calendar_summary(month_key)
        weekday_offset, days_in_month = calendar.monthrange(self.month.year, self.month.month)
        for cell in range(42):
            day = cell - weekday_offset + 1
            if not 1 <= day <= days_in_month:
                calendar_grid.add_widget(Widget(size_hint_y=None, height=dp(48)))
                continue
            entry_date = date(self.month.year, self.month.month, day).isoformat()
            entry = summary.get(entry_date, {})
            parts = entry.get("body_parts", [])
            marker = " ".join(part[:1] for part in parts) or ("休" if entry.get("is_rest_day") else "")
            tone = "primary" if entry_date == self.selected_date else (
                "secondary" if parts or entry.get("is_rest_day") else "neutral"
            )
            calendar_grid.add_widget(
                make_button(
                    f"{day}\n{marker}",
                    lambda _, selected=day: self.select_day(selected),
                    height=48,
                    tone=tone,
                    font_size=11,
                    padding=(dp(2), 0),
                )
            )

        self.content.add_widget(
            section_heading(
                f"{self.selected_date} · 训练详情",
                "休息日" if summary.get(self.selected_date, {}).get("is_rest_day") else "",
            )
        )
        selected = summary.get(self.selected_date, {})
        workouts = selected.get("workouts", [])
        if not workouts:
            message = "今天是休息日。" if selected.get("is_rest_day") else "当天没有训练记录。"
            self.content.add_widget(make_label(message, 14, MUTED, 42))
            return
        for workout in sorted(
            workouts,
            key=lambda item: (item.get("training_time", ""), item["id"]),
        ):
            exercise_rows = []
            for exercise in workout["exercises"]:
                set_log = exercise.get("set_log", [])
                exercise_rows.append((exercise, set_log))
            notes = workout.get("notes", "").strip()
            duration_seconds = workout.get("duration_seconds")
            duration_height = 24
            row_count = 2 + sum(
                1 + max(1, len(set_log)) for _, set_log in exercise_rows
            )
            note_height = (
                max(44, 22 * ((len(notes) + 17) // 18))
                if notes
                else 0
            )
            row_count += bool(notes) + bool(duration_height)
            content_height = (
                30
                + 24
                + sum(
                    26 + 22 * max(1, len(set_log))
                    for _, set_log in exercise_rows
                )
                + note_height
                + duration_height
                + max(0, row_count - 1) * 6
                + 24
            )
            card = SurfaceCard(
                size_hint_y=None,
                height=dp(content_height),
                spacing=dp(6),
                padding=dp(12),
            )
            time_label = workout.get("training_time") or "时间未记录"
            card.add_widget(
                make_label(
                    f"{time_label} · {workout['title']}",
                    15,
                    TEXT,
                    30,
                    True,
                    shorten=True,
                )
            )
            parts = "、".join(PART_NAMES.get(part, part) for part in workout["body_parts"])
            card.add_widget(make_label(parts, 12, MUTED, 24))
            for exercise, set_log in exercise_rows:
                card.add_widget(
                    make_label(
                        f"{exercise['name']}  {exercise['sets']}组×{exercise['reps']}次"
                        f" · {exercise['weight']:g}kg",
                        13,
                        TEXT,
                        26,
                        shorten=True,
                    )
                )
                if set_log:
                    for index, entry in enumerate(set_log, start=1):
                        status = "已完成" if entry["completed"] else "未完成"
                        card.add_widget(
                            make_label(
                                f"第 {index} 组 · {entry['weight']:g}kg × "
                                f"{entry['reps']}次 · {status}",
                                12,
                                MUTED,
                                22,
                                shorten=True,
                            )
                        )
                else:
                    card.add_widget(
                        make_label("逐组数据未记录", 12, MUTED, 22)
                    )
            if notes:
                card.add_widget(
                    make_label(
                        f"备注：{notes}",
                        12,
                        MUTED,
                        note_height,
                    )
                )
            if isinstance(duration_seconds, int):
                card.add_widget(
                    make_label(
                        f"训练时长 {WorkoutScreen._format_duration(duration_seconds)}",
                        12,
                        MUTED,
                        24,
                    )
                )
            else:
                card.add_widget(make_label("训练时长未记录", 12, MUTED, 24))
            self.content.add_widget(card)

    def open_backfill(self, *_: Any) -> None:
        training_date = self.selected_date
        if training_date >= date.today().isoformat():
            self.notify("只能为过去日期补录训练。")
            return
        ExerciseEntryPopup(
            on_add=lambda exercise, part: self._add_backfilled_exercise(
                training_date,
                exercise,
                part,
            ),
            on_save_template=self._save_backfill_template,
        ).open()

    def _add_backfilled_exercise(
        self,
        training_date: str,
        exercise: dict[str, Any],
        body_part: str,
    ) -> bool:
        try:
            self.store.add_historical_exercise(training_date, body_part, exercise)
        except (KeyError, ValueError, FitnessStoreError) as error:
            LOGGER.exception("Unable to add a historical workout entry")
            self.notify(f"补录训练失败：{error}")
            return False
        self.render()
        return True

    def _save_backfill_template(
        self,
        exercise: dict[str, Any],
        body_part: str,
    ) -> bool:
        try:
            self.store.add_plan(f"{exercise['name']} 模板", [body_part], [exercise])
        except (ValueError, FitnessStoreError) as error:
            LOGGER.exception("Unable to save template from history")
            self.notify(f"保存动作模板失败：{error}")
            return False
        self.notify("动作模板已保存到资料库。")
        return True

    def open_restore(self, *_: Any) -> None:
        BackupImportPopup(
            self.store.validate_backup_document,
            self._restore_backup,
        ).open()

    def _restore_backup(self, document: dict[str, Any]) -> None:
        try:
            external_snapshot = export_json(
                self.store.data,
                self.app_ref.user_data_dir,
            )
        except ExportPermissionRequired:
            self._pending_restore_document = document
            self._request_export_permission()
            return
        except ExportError as error:
            LOGGER.exception("Unable to export pre-restore fitness data")
            self.notify(f"无法创建恢复前备份，未执行恢复：{error}")
            return
        if platform == "ios":
            try:
                if not isinstance(external_snapshot, Path):
                    raise ExportError("恢复前备份文件位置无效。")
                share_export(external_snapshot)
            except ExportError as error:
                LOGGER.exception("Unable to share pre-restore fitness data")
                self.notify(f"无法分享恢复前备份，未执行恢复：{error}")
                return
        try:
            self.store.restore_backup(document)
        except (FitnessStoreError, TypeError, ValueError) as error:
            LOGGER.exception("Unable to restore fitness data")
            self.notify(f"恢复备份失败：{error}")
            return
        workout_screen = getattr(self.app_ref, "workout_screen", None)
        if workout_screen is not None:
            workout_screen.refresh_today()
        library_screen = getattr(self.app_ref, "library_screen", None)
        if library_screen is not None:
            library_screen.on_pre_enter()
        self.render()
        if platform == "android":
            self.notify("备份已恢复；恢复前数据已导出到系统“下载”目录。")
        elif platform == "ios":
            self.notify("备份已恢复；系统分享菜单可将恢复前数据存储到“文件”。")
        elif isinstance(external_snapshot, Path):
            self.notify(f"备份已恢复；恢复前数据已导出到：\n{external_snapshot}")
        else:
            self.notify("备份已恢复。")


class LibraryScreen(FitnessScreen):
    def __init__(self, app: Any, **kwargs: Any):
        super().__init__(app, **kwargs)
        self.root_layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=(dp(10), dp(8)),
        )
        self.title_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            spacing=dp(6),
        )
        self.title_row.add_widget(make_label("我的资料库", 20, TEXT, 42, True))
        self.save_today_button = make_button(
            "保存今日为模板",
            self.save_today_as_template,
            height=42,
            tone="secondary",
            font_size=11,
        )
        self.save_today_button.size_hint_x = None
        self.save_today_button.width = dp(112)
        self.title_row.add_widget(self.save_today_button)
        self.root_layout.add_widget(self.title_row)

        tab_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )
        self.template_tab = AppToggleButton("动作模板", size_hint_x=1)
        self.records_tab = AppToggleButton("个人纪录", size_hint_x=1)
        self.template_tab.bind(on_release=lambda *_: self.show_templates())
        self.records_tab.bind(on_release=lambda *_: self.show_records())
        tab_row.add_widget(self.template_tab)
        tab_row.add_widget(self.records_tab)
        self.root_layout.add_widget(tab_row)
        self.template_search = make_input("搜索模板、训练部位或动作")
        self.template_search.bind(text=self._template_search_changed)
        self.scroll, self.content = make_scroll_content()
        self.root_layout.add_widget(self.scroll)
        self.add_widget(self.root_layout)
        self.show_templates()

    def on_pre_enter(self, *_: Any) -> None:
        self.show_templates()

    def show_templates(self) -> None:
        self.template_tab.state = "down"
        self.records_tab.state = "normal"
        self.content.clear_widgets()
        self.content.add_widget(section_heading("动作模板", "选择模板，一键添加到今日训练。"))
        self.content.add_widget(self.template_search)
        self.template_list = GridLayout(
            cols=1,
            spacing=dp(10),
            size_hint_y=None,
        )
        self.template_list.bind(minimum_height=self.template_list.setter("height"))
        self.content.add_widget(self.template_list)
        self._render_template_list()

    def _template_search_changed(self, *_: Any) -> None:
        if hasattr(self, "template_list"):
            self._render_template_list()

    def _render_template_list(self) -> None:
        self.template_list.clear_widgets()
        templates = list(reversed(self.store.data["plans"]))
        query = self.template_search.text.strip().casefold()
        if query:
            templates = [
                template
                for template in templates
                if query in " ".join(
                    [
                        template["title"],
                        *template["body_parts"],
                        *(PART_NAMES.get(part, part) for part in template["body_parts"]),
                        *(exercise["name"] for exercise in template["exercises"]),
                    ]
                ).casefold()
            ]
        if not templates:
            message = (
                "没有匹配的模板，请调整搜索内容。"
                if query
                else "暂无模板，可从添加动作时收藏。"
            )
            self.template_list.add_widget(make_label(message, 14, MUTED, 48))
            return
        for template in templates:
            card = SurfaceCard(
                size_hint_y=None,
                height=dp(142),
                spacing=dp(6),
                padding=dp(12),
            )
            card.add_widget(
                make_label(
                    f"{template['title']}  ·  {len(template['exercises'])} 个动作",
                    16,
                    TEXT,
                    32,
                    True,
                    shorten=True,
                )
            )
            preview = "、".join(item["name"] for item in template["exercises"][:4])
            if len(template["exercises"]) > 4:
                preview += "…"
            parts = "、".join(PART_NAMES.get(part, part) for part in template["body_parts"])
            card.add_widget(make_label(f"{parts}  ·  {preview}", 12, MUTED, 34, shorten=True))
            actions = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(44),
                spacing=dp(8),
            )
            actions.add_widget(
                make_button(
                    "加入今日训练",
                    lambda _, item=template: self.add_template_to_today(item),
                    height=44,
                )
            )
            actions.add_widget(
                make_button(
                    "删除",
                    lambda _, item=template: self.delete_template(item["id"]),
                    height=44,
                    tone="danger",
                )
            )
            card.add_widget(actions)
            self.template_list.add_widget(card)

    def show_records(self) -> None:
        self.template_tab.state = "normal"
        self.records_tab.state = "down"
        self.content.clear_widgets()
        self.content.add_widget(section_heading("个人纪录", "按动作展示目前记录的最高重量。"))
        records = self.store.personal_records()
        if not records:
            self.content.add_widget(make_label("记录训练后，会在这里显示个人纪录。", 14, MUTED, 48))
            return
        for record in records:
            card = SurfaceCard(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(76),
                spacing=dp(8),
                padding=dp(14),
            )
            details = BoxLayout(orientation="vertical")
            details.add_widget(make_label(record["name"], 15, TEXT, 28, True, shorten=True))
            details.add_widget(make_label(f"{record['date']} 更新", 12, MUTED, 24))
            card.add_widget(details)
            card.add_widget(
                make_label(f"{record['weight']:g} kg", 17, PRIMARY, 36, True)
            )
            self.content.add_widget(card)

    def add_template_to_today(self, template: dict[str, Any]) -> None:
        today = date.today().isoformat()
        has_finished_workout = any(
            item["date"] == today and item["finished"]
            for item in self.store.data["workouts"]
        )
        if self.store.active_workout(today) is None and has_finished_workout:
            ConfirmActionPopup(
                "开始新的训练记录？",
                "今天已有已完成的训练。添加此模板会新建一条训练记录。",
                "开始新训练",
                lambda: self._add_template_to_today(template),
                confirm_tone="primary",
            ).open()
            return
        self._add_template_to_today(template)

    def _add_template_to_today(self, template: dict[str, Any]) -> None:
        try:
            self.store.add_daily_exercises(
                date.today().isoformat(),
                template["body_parts"],
                template["exercises"],
            )
        except (ValueError, FitnessStoreError) as error:
            LOGGER.exception("Unable to add template to today's workout")
            self.notify(f"添加模板失败：{error}")
            return
        self.notify("模板动作已添加到今日训练。")
        self.app_ref.workout_screen.refresh_today()

    def delete_template(self, template_id: str) -> None:
        template = next(
            (
                item for item in self.store.data["plans"]
                if item["id"] == template_id
            ),
            None,
        )
        if template is None:
            self.notify("模板不存在或已删除。")
            self.show_templates()
            return
        ConfirmActionPopup(
            "确认删除模板",
            f"删除“{template['title']}”及其动作配置？此操作无法撤销。",
            "删除模板",
            lambda: self._delete_template_confirmed(template_id),
        ).open()

    def _delete_template_confirmed(self, template_id: str) -> None:
        try:
            self.store.delete("plans", template_id)
        except (KeyError, FitnessStoreError) as error:
            LOGGER.exception("Unable to delete workout template")
            self.notify(f"删除模板失败：{error}")
            return
        self.show_templates()

    def save_today_as_template(self, *_: Any) -> None:
        workouts = [
            item for item in self.store.data["workouts"]
            if item["date"] == date.today().isoformat()
        ]
        if not workouts:
            self.notify("今天还没有训练动作，暂时无法保存整套训练模板。")
            return
        exercises = [exercise for workout in workouts for exercise in workout["exercises"]]
        parts = list(dict.fromkeys(
            part for workout in workouts for part in workout["body_parts"]
        ))
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        content.add_widget(make_label("为今天的整套训练命名。", 14, MUTED, 34))
        name_input = make_input("模板名称，例如：推胸日 A")
        content.add_widget(name_input)
        error = make_label("", 12, MUTED, 28)
        content.add_widget(error)
        popup = Popup(
            title="保存训练模板",
            content=content,
            size_hint=(0.94, None),
            height=dp(230),
            background="",
            background_color=SURFACE,
            title_color=TEXT,
            title_font=font_name(),
            separator_color=BORDER,
        )

        def save(*_: Any) -> None:
            try:
                self.store.add_plan(name_input.text, parts, exercises)
            except ValueError as validation_error:
                error.text = str(validation_error)
                return
            except FitnessStoreError as storage_error:
                LOGGER.exception("Unable to save today's workout as a template")
                error.text = f"保存失败：{storage_error}"
                return
            popup.dismiss()
            self.show_templates()
            self.notify("今日训练已保存为模板。")

        content.add_widget(make_button("保存模板", save, height=46))
        popup.open()
