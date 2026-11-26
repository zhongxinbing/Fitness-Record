"""FastAPI 应用工厂。

集中完成：日志、静态资源、模板、路由注册、健康检查与统一异常处理。
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import APP_VERSION, PROJECT_ROOT, settings
from app.database import get_connection, init_db, table_names
from app.routers import auth, bodies, plans, stats

logger = logging.getLogger("fitness")


def create_app() -> FastAPI:
    """创建并配置应用实例。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = FastAPI(title=settings.app_name, debug=settings.debug)

    # CORS：仅在显式配置来源时开放，默认同源访问。
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    static_dir = PROJECT_ROOT / "app" / "static"
    template_dir = PROJECT_ROOT / "app" / "templates"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    templates = Jinja2Templates(directory=str(template_dir))

    # 路由注册
    app.include_router(auth.router)
    app.include_router(plans.router)
    app.include_router(bodies.router)
    app.include_router(stats.router)

    init_db()
    # 启动横幅：版本、库文件、表数量一目了然，便于确认“跑的是哪一版、用的哪个库”
    try:
        conn = get_connection()
        try:
            logger.info(
                "启动完成 v%s | 库文件：%s | 表数量：%s",
                APP_VERSION, settings.resolved_db_path, len(table_names(conn)),
            )
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception("启动自检读取数据库失败：%s", settings.resolved_db_path)

    @app.exception_handler(sqlite3.Error)
    def _sqlite_error(request: Request, exc: sqlite3.Error) -> JSONResponse:
        """数据库层错误统一返回 503 + 可读提示，而不是抛出 500 traceback。"""
        logger.exception("数据库操作失败: %s", exc)
        current = getattr(request, "url", None)
        return JSONResponse(
            status_code=503,
            content={
                "detail": f"数据库不可用：{exc}",
                "hint": "运行 python scripts/doctor.py 体检，必要时 python scripts/doctor.py --fix 修复；"
                        f"当前库文件：{settings.resolved_db_path}",
                "path": str(getattr(current, 'path', '')),
            },
        )

    @app.get("/health", tags=["system"])
    def health() -> dict:
        # version / db 便于排查“跑的是不是新版、用的是哪个库文件”
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": APP_VERSION,
            "db": str(settings.resolved_db_path),
        }

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.app_name})

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

    return app
