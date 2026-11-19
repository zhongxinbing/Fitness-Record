"""Persistent rest timer with an Android background-service handoff."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from kivy.clock import Clock
from kivy.utils import platform

from fitness_ui.android_timer import (
    AndroidTimerError,
    post_completion_notification,
    request_timer_permissions,
    start_background_service,
)


LOGGER = logging.getLogger(__name__)


class RestTimerError(ValueError):
    """Raised when a rest timer cannot be started, stopped, or restored."""


def read_timer_state(path: str | Path) -> dict[str, Any] | None:
    state_path = Path(path)
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RestTimerError(f"无法读取休息计时状态：{error}") from error
    if not isinstance(state, dict):
        raise RestTimerError("休息计时状态格式无效。")
    return state


def write_timer_state(path: str | Path, state: dict[str, Any]) -> None:
    state_path = Path(path)
    temporary: Path | None = None
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=state_path.parent,
            prefix=f".{state_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, state_path)
    except (OSError, TypeError, ValueError) as error:
        raise RestTimerError(f"无法保存休息计时状态：{error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove rest timer temp file %s", temporary, exc_info=True)


def remove_timer_state(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as error:
        raise RestTimerError(f"无法清理休息计时状态：{error}") from error


class RestTimerController:
    def __init__(self, app: Any, state_path: str | Path):
        self.app = app
        self.state_path = Path(state_path)
        self.state: dict[str, Any] | None = None
        self._event: Any = None
        self._last_finished_id: str | None = None

    def start(self, exercise: str, duration: int) -> None:
        if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
            raise RestTimerError("该动作的休息时间必须大于 0 秒。")
        if duration > 3600:
            raise RestTimerError("单次休息时间不能超过 60 分钟。")
        if self.state is not None and self.state.get("status") == "running":
            raise RestTimerError("已有休息计时正在运行，请先停止后再启动新的计时。")
        if not exercise.strip():
            raise RestTimerError("请先填写动作名称。")

        if platform == "android":
            try:
                request_timer_permissions()
            except AndroidTimerError as error:
                raise RestTimerError(str(error)) from error

        state = {
            "id": uuid.uuid4().hex,
            "exercise": exercise.strip(),
            "duration": duration,
            "deadline": time.time() + duration,
            "status": "running",
            "notified": False,
        }
        write_timer_state(self.state_path, state)
        if platform == "android":
            try:
                start_background_service(self._service_payload(state))
            except AndroidTimerError as error:
                remove_timer_state(self.state_path)
                raise RestTimerError(str(error)) from error
        self.state = state
        self._start_clock()
        self._update_app()

    def restore(self) -> None:
        try:
            state = read_timer_state(self.state_path)
        except RestTimerError as error:
            LOGGER.exception("Unable to restore rest timer")
            self.app.on_rest_timer_error(str(error))
            return
        if state is None:
            return
        if state.get("status") == "completed":
            try:
                remove_timer_state(self.state_path)
            except RestTimerError as error:
                LOGGER.exception("Unable to clean up completed rest timer")
                self.app.on_rest_timer_error(str(error))
                return
            if not state.get("notified") and state.get("id") != self._last_finished_id:
                self._last_finished_id = str(state.get("id", ""))
                self.app.on_rest_timer_finished(str(state.get("exercise", "")))
            return
        if state.get("status") != "running":
            try:
                remove_timer_state(self.state_path)
            except RestTimerError as error:
                LOGGER.exception("Unable to clean up stopped rest timer")
                self.app.on_rest_timer_error(str(error))
            return
        deadline = state.get("deadline")
        if (
            not isinstance(deadline, (int, float))
            or isinstance(deadline, bool)
            or not math.isfinite(deadline)
            or not isinstance(state.get("exercise"), str)
            or not isinstance(state.get("id"), str)
            or not state["id"]
        ):
            error = RestTimerError("休息计时状态缺少必要信息。")
            LOGGER.error("%s", error)
            self.app.on_rest_timer_error(str(error))
            return
        self.state = state
        if platform == "android":
            try:
                request_timer_permissions()
                start_background_service(self._service_payload(state))
            except AndroidTimerError as error:
                LOGGER.warning("Unable to restore the Android rest-timer service: %s", error)
                self.app.on_rest_timer_error(str(error))
        self._start_clock()
        self._update_app()
        self._tick(0)

    def refresh(self) -> None:
        if self.state is not None:
            self._tick(0)
            return
        try:
            state = read_timer_state(self.state_path)
        except RestTimerError as error:
            LOGGER.exception("Unable to refresh rest timer")
            self.app.on_rest_timer_error(str(error))
            return
        if state is None:
            self._update_app()
            return
        if state.get("status") == "completed":
            exercise = str(state.get("exercise", ""))
            try:
                remove_timer_state(self.state_path)
            except RestTimerError as error:
                LOGGER.exception("Unable to clean up completed rest timer")
                self.app.on_rest_timer_error(str(error))
                return
            if state.get("id") != self._last_finished_id:
                self._last_finished_id = str(state.get("id", ""))
                self.app.on_rest_timer_finished(exercise)
        elif state.get("status") == "running":
            self.restore()

    def cancel(self) -> None:
        if self.state is None:
            return
        cancelled = {**self.state, "status": "cancelled"}
        write_timer_state(self.state_path, cancelled)
        self._cancel_clock()
        self.state = None
        self._update_app()

    def extend(self, seconds: int = 30) -> None:
        if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
            raise RestTimerError("延长时间必须是正整数秒。")
        if self.state is None or self.state.get("status") != "running":
            raise RestTimerError("当前没有正在运行的休息计时。")
        duration = int(self.state["duration"]) + seconds
        if duration > 3600:
            raise RestTimerError("单次休息计时不能超过 60 分钟。")
        updated_state = {
            **self.state,
            "duration": duration,
            "deadline": float(self.state["deadline"]) + seconds,
        }
        write_timer_state(self.state_path, updated_state)
        self.state = updated_state
        self._update_app()

    def _service_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "state_path": str(self.state_path),
        }

    def _start_clock(self) -> None:
        self._cancel_clock()
        self._event = Clock.schedule_interval(self._tick, 0.25)

    def _cancel_clock(self) -> None:
        if self._event is not None:
            self._event.cancel()
            self._event = None

    def _update_app(self) -> None:
        remaining = self._remaining()
        self.app.update_rest_timer(self.state, remaining)

    def _remaining(self) -> int:
        if self.state is None:
            return 0
        return max(0, int(self.state["deadline"] - time.time() + 0.999))

    def _tick(self, _delta: float) -> bool:
        if self.state is None:
            self._event = None
            return False
        try:
            persisted = read_timer_state(self.state_path)
        except RestTimerError as error:
            LOGGER.exception("Unable to read rest timer during countdown")
            self._cancel_clock()
            self.state = None
            self._update_app()
            self.app.on_rest_timer_error(str(error))
            return False
        if (
            persisted is None
            or persisted.get("id") != self.state["id"]
            or persisted.get("status") != "running"
        ):
            self._cancel_clock()
            exercise = self.state["exercise"]
            timer_id = str(self.state["id"])
            completed = (
                persisted is not None
                and persisted.get("id") == timer_id
                and persisted.get("status") == "completed"
            )
            self.state = None
            self._update_app()
            if completed:
                self._last_finished_id = timer_id
                try:
                    remove_timer_state(self.state_path)
                except RestTimerError as error:
                    LOGGER.exception("Unable to clean up completed rest timer")
                    self.app.on_rest_timer_error(str(error))
                self.app.on_rest_timer_finished(exercise)
            return False

        remaining = self._remaining()
        if remaining > 0:
            self._update_app()
            return True
        self._cancel_clock()
        exercise = self.state["exercise"]
        if platform == "android":
            notified = bool(persisted.get("notified"))
            try:
                if not notified:
                    post_completion_notification(
                        "休息时间结束",
                        f"{exercise} 休息结束，可以继续训练。",
                    )
                    notified = True
            except AndroidTimerError as error:
                LOGGER.exception("Unable to send rest timer notification")
                self.app.on_rest_timer_error(str(error))
            try:
                write_timer_state(
                    self.state_path,
                    {**persisted, "status": "completed", "notified": notified},
                )
            except RestTimerError as error:
                LOGGER.exception("Unable to save completed rest timer state")
                self.app.on_rest_timer_error(str(error))
        else:
            try:
                remove_timer_state(self.state_path)
            except RestTimerError as error:
                LOGGER.exception("Unable to remove finished rest timer state")
                self.app.on_rest_timer_error(str(error))
        self.state = None
        self._update_app()
        self._last_finished_id = str(persisted.get("id", ""))
        self.app.on_rest_timer_finished(exercise)
        return False
