"""服务启动入口。

运行: python main.py
"""
from __future__ import annotations

import sys

import uvicorn

from app.config import settings

# python main.py --doctor：先体检数据库再启动，排查缺表/缺列最省事
if __name__ == "__main__" and "--doctor" in sys.argv:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    from scripts.doctor import main as doctor_main

    raise SystemExit(doctor_main())

from app import create_app  # noqa: E402  (--doctor 分支要先走掉)

app = create_app()

if __name__ == "__main__":
    # 非调试时直接传 app 对象：避免 uvicorn 再 import 一次 main，导致启动横幅重复
    if settings.debug:
        uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
    else:
        uvicorn.run(app, host=settings.host, port=settings.port)
