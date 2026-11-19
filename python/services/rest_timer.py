"""Foreground service that keeps an exercise rest timer alive on Android."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fitness_ui.android_timer import AndroidTimerError, post_completion_notification


LOGGER = logging.getLogger("fitness.rest_timer_service")


def _read_state(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        LOGGER.exception("Cannot read rest timer state")
        return None
    return value if isinstance(value, dict) else None


def _write_state(path: Path, state: dict[str, Any]) -> None:
    from fitness_ui.rest_timer import write_timer_state

    write_timer_state(path, state)


def run() -> None:
    raw_argument = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        arguments = json.loads(raw_argument)
        state_path = Path(arguments["state_path"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        LOGGER.exception("Invalid rest timer service arguments")
        return

    from jnius import autoclass

    service = autoclass("org.kivy.android.PythonService").mService
    Context = autoclass("android.content.Context")
    PowerManager = autoclass("android.os.PowerManager")
    power_manager = service.getSystemService(Context.POWER_SERVICE)
    wake_lock = power_manager.newWakeLock(
        PowerManager.PARTIAL_WAKE_LOCK,
        "FitnessRecord:RestTimer",
    )
    wake_lock.acquire()
    try:
        while True:
            state = _read_state(state_path)
            if state is None or state.get("status") != "running":
                if state is not None:
                    state_path.unlink(missing_ok=True)
                return

            remaining = float(state["deadline"]) - time.time()
            if remaining <= 0:
                notified = bool(state.get("notified"))
                try:
                    if not notified:
                        post_completion_notification(
                            "休息时间结束",
                            f"{state['exercise']} 休息结束，可以继续训练。",
                            service_context=service,
                        )
                        notified = True
                except AndroidTimerError:
                    LOGGER.exception("Unable to send rest timer completion notification")
                _write_state(
                    state_path,
                    {**state, "status": "completed", "notified": notified},
                )
                return
            time.sleep(min(1.0, remaining))
    finally:
        if wake_lock.isHeld():
            wake_lock.release()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
