"""Reusable accessible Kivy controls and page layout helpers."""

from __future__ import annotations

from typing import Any

from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from fitness_data import FitnessStore
from fitness_ui.theme import (
    ACCENT_SOFT, BORDER, DANGER, MUTED, PRIMARY, PRIMARY_DARK, SURFACE, TEXT,
    WHITE, font_name,
)


class SurfaceCard(BoxLayout):
    def __init__(self, **kwargs: Any):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", dp(16))
        kwargs.setdefault("spacing", dp(10))
        super().__init__(**kwargs)
        with self.canvas.before:
            self._surface_color = Color(*SURFACE)
            self._surface_shape = RoundedRectangle(radius=[dp(18)])
        self.bind(pos=self._update_surface, size=self._update_surface)

    def _update_surface(self, *_: Any) -> None:
        self._surface_shape.pos = self.pos
        self._surface_shape.size = self.size


class AppButton(Button):
    TONES = {
        "primary": (PRIMARY, WHITE),
        "secondary": (ACCENT_SOFT, PRIMARY_DARK),
        "danger": (DANGER, WHITE),
        "navigation": (SURFACE, MUTED),
        "navigation_active": (PRIMARY, WHITE),
        "neutral": ((0.91, 0.93, 0.91, 1), TEXT),
    }

    def __init__(
        self,
        text: str,
        callback: Any,
        *,
        tone: str = "primary",
        height: int = 48,
        font_size: int = 15,
        **kwargs: Any,
    ):
        self.tone = tone
        self._fill = Color()
        self._shape = RoundedRectangle(radius=[dp(14)])
        super().__init__(
            text=text,
            font_name=font_name(),
            font_size=dp(font_size),
            size_hint_y=None,
            height=dp(height),
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            color=WHITE,
            **kwargs,
        )
        with self.canvas.before:
            self.canvas.before.add(self._fill)
            self.canvas.before.add(self._shape)
        self.bind(pos=self._update_shape, size=self._update_shape, state=self._update_fill)
        self.bind(on_release=callback)
        self._update_fill()

    def set_tone(self, tone: str) -> None:
        if tone not in self.TONES:
            raise ValueError(f"Unknown button tone: {tone}")
        self.tone = tone
        self._update_fill()

    def _update_shape(self, *_: Any) -> None:
        self._shape.pos = self.pos
        self._shape.size = self.size

    def _update_fill(self, *_: Any) -> None:
        background, foreground = self.TONES[self.tone]
        if self.state == "down" and self.tone in ("primary", "navigation_active"):
            background = PRIMARY_DARK
        self._fill.rgba = background
        self.color = foreground


class AppToggleButton(ToggleButton):
    def __init__(self, text: str, **kwargs: Any):
        self._fill = Color()
        self._shape = RoundedRectangle(radius=[dp(12)])
        super().__init__(
            text=text,
            font_name=font_name(),
            font_size=dp(14),
            size_hint_y=None,
            height=dp(44),
            group=None,
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            color=TEXT,
            **kwargs,
        )
        with self.canvas.before:
            self.canvas.before.add(self._fill)
            self.canvas.before.add(self._shape)
        self.bind(pos=self._update_shape, size=self._update_shape, state=self._update_fill)
        self._update_fill()

    def _update_shape(self, *_: Any) -> None:
        self._shape.pos = self.pos
        self._shape.size = self.size

    def _update_fill(self, *_: Any) -> None:
        self._fill.rgba = PRIMARY if self.state == "down" else ACCENT_SOFT
        self.color = WHITE if self.state == "down" else PRIMARY_DARK


def make_label(
    text: str,
    size: int = 16,
    color: tuple[float, float, float, float] = TEXT,
    height: int | None = None,
    bold: bool = False,
    *,
    shorten: bool = False,
) -> Label:
    label = Label(
        text=text,
        font_name=font_name(),
        font_size=dp(size),
        color=color,
        bold=bold,
        size_hint_y=None,
        height=dp(height or size * 2),
        halign="left",
        valign="middle",
        shorten=shorten,
        shorten_from="right",
        text_size=(None, None),
    )
    label.bind(width=lambda instance, width: setattr(instance, "text_size", (width, None)))
    return label


def make_button(
    text: str,
    callback: Any,
    *,
    height: int = 48,
    tone: str = "primary",
    font_size: int = 15,
    **kwargs: Any,
) -> AppButton:
    return AppButton(
        text,
        callback,
        height=height,
        tone=tone,
        font_size=font_size,
        **kwargs,
    )


class UndoBanner(SurfaceCard):
    def __init__(self):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=0,
            spacing=dp(8),
            padding=(dp(10), dp(3)),
            opacity=0,
        )
        self.message = make_label("", 12, TEXT, 40, shorten=True)
        self.add_widget(self.message)
        self.undo_button = make_button(
            "撤销",
            self.undo,
            height=40,
            tone="secondary",
            font_size=12,
        )
        self.undo_button.size_hint_x = None
        self.undo_button.width = dp(58)
        self.add_widget(self.undo_button)
        self._undo_action: Any = None
        self._timeout_event = None

    def show(self, message: str, undo_action: Any, duration: float = 6) -> None:
        if self._timeout_event is not None:
            self._timeout_event.cancel()
        self.message.text = message
        self._undo_action = undo_action
        self.height = dp(48)
        self.opacity = 1
        self._timeout_event = Clock.schedule_once(self.hide, duration)

    def hide(self, *_: Any) -> None:
        self._timeout_event = None
        self._undo_action = None
        self.height = 0
        self.opacity = 0

    def undo(self, *_: Any) -> None:
        undo_action = self._undo_action
        self.hide()
        if undo_action is not None:
            undo_action()


def make_input(
    hint: str,
    text: str = "",
    *,
    numeric: bool = False,
    multiline: bool = False,
) -> TextInput:
    return TextInput(
        hint_text=hint,
        text=text,
        font_name=font_name(),
        font_size=dp(15),
        multiline=multiline,
        input_filter="float" if numeric else None,
        input_type="number" if numeric else "text",
        keyboard_suggestions=not numeric,
        size_hint_y=None,
        height=dp(88 if multiline else 50),
        padding=(dp(14), dp(12)),
        background_normal="",
        background_active="",
        background_color=(0.96, 0.97, 0.96, 1),
        foreground_color=TEXT,
        cursor_color=PRIMARY,
        hint_text_color=MUTED,
    )


def section_heading(title: str, subtitle: str | None = None) -> BoxLayout:
    heading = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
    heading.add_widget(make_label(title, 17, TEXT, 30, True))
    if subtitle:
        heading.add_widget(make_label(subtitle, 13, MUTED, 24))
    heading.height = sum(child.height for child in heading.children) + dp(2)
    return heading


def make_scroll_content() -> tuple[ScrollView, GridLayout]:
    scroll = ScrollView(
        do_scroll_x=False,
        scroll_y=1,
        bar_width=dp(3),
        scroll_type=["bars", "content"],
    )
    content = GridLayout(
        cols=1,
        orientation="lr-tb",
        spacing=dp(12),
        padding=(dp(16), dp(12), dp(16), dp(20)),
        size_hint_y=None,
    )
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)

    def resize_content(_scroll: ScrollView, width: float) -> None:
        content.width = width
        content.do_layout()

    scroll.bind(width=resize_content)
    return scroll, content


class FitnessScreen(Screen):
    def __init__(self, app: Any, **kwargs: Any):
        super().__init__(**kwargs)
        self.app_ref = app

    def add_page_scroll(self, scroll: ScrollView) -> None:
        self.add_widget(scroll)
        self.bind(
            pos=scroll.setter("pos"),
            size=scroll.setter("size"),
        )

    @property
    def store(self) -> FitnessStore:
        return self.app_ref.store

    def notify(self, message: str, *, title: str = "提示") -> None:
        body = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        body.add_widget(make_label(message, 15, TEXT, 70))
        popup = Popup(
            title=title,
            content=body,
            size_hint=(0.88, None),
            height=dp(176),
            background="",
            title_font=font_name(),
            title_color=TEXT,
            separator_color=BORDER,
            background_color=SURFACE,
        )
        body.add_widget(make_button("知道了", lambda *_: popup.dismiss(), height=46, tone="primary"))
        popup.open()
