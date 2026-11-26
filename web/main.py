"""服务启动入口。

运行: python main.py
"""
from __future__ import annotations

import uvicorn

from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
