"""应用配置层。

通过环境变量覆盖默认值，符合 12-Factor App 约定；未注入环境变量时使用本地开发默认值。
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """运行配置。

    属性:
        app_name: 应用名称。
        debug: 是否开启调试模式。
        host: 监听地址。
        port: 监听端口。
        db_path: SQLite 数据库文件路径（相对项目根目录解析）。
        cors_origins: 允许的跨域来源，逗号分隔；默认为空表示不额外开放。
        timezone: 业务时区，用于“今天”的判定，避免服务器 UTC 时区造成日期偏差。
        session_days: 登录会话有效期（天）。
        cookie_secure: 是否给会话 Cookie 加 Secure 标记（部署在 HTTPS 时开启）。
    """

    app_name: str = "健身记录"
    debug: bool = False
    host: str = "0.0.0.0"
    # 云平台（Render/Heroku/Railway 等）统一注入 PORT，优先读它，其次 FIT_PORT
    port: int = Field(default=8000, validation_alias=AliasChoices("PORT", "FIT_PORT"))
    db_path: str = "data/fitness.db"
    cors_origins: str = ""
    timezone: str = "Asia/Shanghai"
    session_days: int = 7
    cookie_secure: bool = False

    model_config = SettingsConfigDict(env_prefix="FIT_", env_file=".env", extra="ignore")

    @property
    def resolved_db_path(self) -> Path:
        """返回数据库文件的绝对路径，并确保父目录存在。"""
        path = Path(self.db_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


# 版本号：升级后可用 /health 确认跑的是哪一版
APP_VERSION = "7.2"

# 项目根目录：fitness_tracker/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


settings = Settings()


def local_today() -> date:
    """返回业务时区下的“今天”，时区不可用时退回服务器本地日期。"""
    try:
        return datetime.now(ZoneInfo(settings.timezone)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return date.today()
