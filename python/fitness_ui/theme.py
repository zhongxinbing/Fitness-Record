"""Shared visual tokens and platform font setup."""

from pathlib import Path

from kivy.core.text import LabelBase

BACKGROUND = (0.95, 0.96, 0.94, 1)
SURFACE = (1, 1, 1, 1)
TEXT = (0.12, 0.17, 0.17, 1)
MUTED = (0.43, 0.49, 0.49, 1)
PRIMARY = (0.10, 0.46, 0.40, 1)
PRIMARY_DARK = (0.07, 0.36, 0.31, 1)
ACCENT_SOFT = (0.88, 0.94, 0.91, 1)
DANGER = (0.70, 0.24, 0.20, 1)
BORDER = (0.88, 0.90, 0.87, 1)
WHITE = (1, 1, 1, 1)

_FONT_NAME = "Roboto"


def register_cjk_font() -> str:
    global _FONT_NAME
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path("/system/fonts/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    )
    for candidate in candidates:
        if candidate.exists():
            LabelBase.register(name="FitnessCJK", fn_regular=str(candidate))
            _FONT_NAME = "FitnessCJK"
            break
    return _FONT_NAME


def font_name() -> str:
    return _FONT_NAME
