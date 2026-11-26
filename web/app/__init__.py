"""FastAPI 应用工厂。

集中完成：日志、静态资源、模板、路由注册、健康检查与统一异常处理。
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import PROJECT_ROOT, settings
from app.database import init_db
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

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "app": settings.app_name}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.app_name})

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

    return app
