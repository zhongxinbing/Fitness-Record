"""Application shell with three-tab navigation and a full-screen rest timer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, ScreenManager
from kivy.utils import platform
from kivy.uix.widget import Widget

from fitness_data import FitnessStore, FitnessStoreError
from fitness_ui.rest_timer import RestTimerController
from fitness_ui.screens import CalendarHistoryScreen, LibraryScreen, WorkoutScreen
from fitness_ui.theme import BACKGROUND, BORDER, PRIMARY, SURFACE, TEXT, register_cjk_font
from fitness_ui.widgets import AppButton, SurfaceCard, make_button, make_label


LOGGER = logging.getLogger(__name__)
NAV_ITEMS = (
    ("今日", "workout"),
    ("历史", "history"),
    ("资料库", "library"),
)


class TimerProgress(Widget):
    progress = NumericProperty(0)

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        with self.canvas:
            Color(*BORDER)
            self.track = RoundedRectangle(radius=[dp(6)])
            self.fill_color = Color(*PRIMARY)
            self.fill = RoundedRectangle(radius=[dp(6)])
        self.bind(pos=self._update, size=self._update, progress=self._update)

    def _update(self, *_: object) -> None:
        self.track.pos = self.pos
        self.track.size = self.size
        self.fill.pos = self.pos
        self.fill.size = (self.width * min(1, max(0, self.progress)), self.height)


class RestTimerPopup(Popup):
    def __init__(self, app: FitnessRecordApp):
        self.app_ref = app
        self.previous_screensaver_state = Window.allow_screensaver
        Window.allow_screensaver = False
        content = BoxLayout(
            orientation="vertical",
            padding=(dp(22), dp(28)),
            spacing=dp(18),
        )
        self.progress = TimerProgress(size_hint_y=None, height=dp(12))
        content.add_widget(self.progress)
        content.add_widget(WidgetSpacer())
        self.exercise_label = make_label("", 16, TEXT, 38, True)
        content.add_widget(self.exercise_label)
        self.countdown = make_label("00:00", 58, PRIMARY, 92, True)
        self.countdown.halign = "center"
        content.add_widget(self.countdown)
        content.add_widget(WidgetSpacer())
        actions = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(58),
            spacing=dp(10),
        )
        actions.add_widget(
            make_button("+ 30 秒", self.extend, height=58, tone="secondary", font_size=16)
        )
        actions.add_widget(
            make_button("跳过休息", self.skip, height=58, tone="primary", font_size=16)
        )
        content.add_widget(actions)
        content.add_widget(
            make_label("计时期间保持屏幕常亮；结束时通过系统提醒通知。", 12, TEXT, 32)
        )
        super().__init__(
            title="休息计时",
            content=content,
            size_hint=(1, 1),
            auto_dismiss=False,
            separator_height=0,
            background="",
            background_color=SURFACE,
            title_color=TEXT,
            title_font=register_cjk_font(),
            separator_color=BORDER,
        )
        self.bind(on_dismiss=self._restore_screensaver)
        self.refresh(app.timer_controller.state, app.timer_controller._remaining())

    def refresh(self, state: dict[str, object] | None, remaining: int) -> None:
        if state is None:
            return
        duration = max(1, int(state.get("duration", remaining)))
        self.progress.progress = min(1, max(0, (duration - remaining) / duration))
        self.exercise_label.text = str(state.get("exercise", "休息中"))
        minutes, seconds = divmod(remaining, 60)
        self.countdown.text = f"{minutes:02d}:{seconds:02d}"

    def extend(self, *_: object) -> None:
        try:
            self.app_ref.timer_controller.extend(30)
        except ValueError as error:
            self.app_ref.workout_screen.notify(str(error))

    def skip(self, *_: object) -> None:
        try:
            self.app_ref.timer_controller.cancel()
        except ValueError as error:
            self.app_ref.workout_screen.notify(str(error))
            return
        self.dismiss()

    def _restore_screensaver(self, *_: object) -> None:
        Window.allow_screensaver = self.previous_screensaver_state
        if self.app_ref.timer_popup is self:
            self.app_ref.timer_popup = None


class WidgetSpacer(BoxLayout):
    def __init__(self):
        super().__init__(size_hint_y=1)


class FitnessRecordApp(App):
    title = "健身记录"
    store: FitnessStore

    def build(self) -> BoxLayout:
        register_cjk_font()
        try:
            self.store = FitnessStore(Path(self.user_data_dir) / "fitness_record.json")
        except FitnessStoreError as error:
            LOGGER.exception("Unable to initialize the local fitness store")
            return self._build_storage_error(error)

        Window.clearcolor = BACKGROUND
        if platform == "android":
            Window.softinput_mode = "below_target"
        self.timer_popup: RestTimerPopup | None = None
        root = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=(dp(10), dp(8)),
        )
        self.manager = ScreenManager(transition=NoTransition())
        self.workout_screen = WorkoutScreen(self, name="workout")
        self.history_screen = CalendarHistoryScreen(self, name="history")
        self.library_screen = LibraryScreen(self, name="library")
        for screen in (
            self.workout_screen,
            self.history_screen,
            self.library_screen,
        ):
            self.manager.add_widget(screen)
        root.add_widget(self.manager)
        root.add_widget(self._build_navigation())
        self.manager.bind(current=self._sync_navigation)
        self._sync_navigation()
        self.timer_controller = RestTimerController(
            self,
            Path(self.user_data_dir) / "rest_timer.json",
        )
        Clock.schedule_once(lambda _delta: self.timer_controller.restore(), 0)
        return root

    def open_rest_timer(self) -> None:
        if self.timer_popup is not None:
            self.timer_popup.refresh(
                self.timer_controller.state,
                self.timer_controller._remaining(),
            )
            return
        self.timer_popup = RestTimerPopup(self)
        self.timer_popup.open()

    def update_rest_timer(
        self,
        state: dict[str, object] | None,
        remaining: int,
    ) -> None:
        if state is None:
            if self.timer_popup is not None:
                self.timer_popup.dismiss()
            return
        if self.timer_popup is None:
            self.open_rest_timer()
        if self.timer_popup is not None:
            self.timer_popup.refresh(state, remaining)

    def on_rest_timer_finished(self, exercise: str) -> None:
        if self.timer_popup is not None:
            self.timer_popup.dismiss()
        self.workout_screen.notify(
            f"{exercise} 休息时间已结束，可以继续训练。",
            title="计时完成",
        )

    def on_rest_timer_error(self, message: str) -> None:
        self.workout_screen.notify(message, title="休息计时")

    def on_resume(self) -> bool:
        if hasattr(self, "timer_controller"):
            self.timer_controller.refresh()
        return True

    def on_pause(self) -> bool:
        return True

    def _build_navigation(self) -> SurfaceCard:
        navigation = SurfaceCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(64),
            padding=(dp(6), dp(6)),
            spacing=dp(6),
        )
        self._nav_buttons: dict[str, AppButton] = {}
        for label, screen_name in NAV_ITEMS:
            button = make_button(
                label,
                lambda _, target=screen_name: setattr(self.manager, "current", target),
                height=50,
                tone="navigation",
                font_size=13,
            )
            button.size_hint_x = 1
            navigation.add_widget(button)
            self._nav_buttons[screen_name] = button
        return navigation

    def _sync_navigation(self, *_: object) -> None:
        if not hasattr(self, "_nav_buttons"):
            return
        for screen_name, button in self._nav_buttons.items():
            button.set_tone(
                "navigation_active" if screen_name == self.manager.current else "navigation"
            )

    def _build_storage_error(self, error: FitnessStoreError) -> BoxLayout:
        Window.clearcolor = BACKGROUND
        root = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(16))
        card = SurfaceCard(size_hint_y=None, height=dp(300))
        card.add_widget(make_label("无法打开本机健身数据", 22, PRIMARY, 48, True))
        card.add_widget(
            make_label(
                f"为保护已有记录，应用没有重置或覆盖数据。\n\n{error}\n\n"
                "请先备份应用数据文件，再检查文件或联系支持人员。",
                15,
                TEXT,
                150,
            )
        )
        card.add_widget(
            make_button("退出应用", lambda *_: self.stop(), height=48, tone="primary")
        )
        root.add_widget(card)
        return root
