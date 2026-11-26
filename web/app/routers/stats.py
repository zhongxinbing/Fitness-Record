"""统计聚合 API 路由。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.auth import current_user
from app.config import local_today
from app.database import get_db
from app.models import StatsOut
from app.repository import StatsRepository

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut, summary="历史页概览统计")
def summary(
    conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> dict:
    return StatsRepository(conn, local_today(), user["id"]).summary()
