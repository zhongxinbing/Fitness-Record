"""鉴权依赖：从 Cookie 会话解析当前用户。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.database import get_db
from app.repository import AuthRepository
from app.security import SESSION_COOKIE, hash_token


def current_user(
    request: Request, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    """校验会话 Cookie，返回 {id, username}；无效则 401。"""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Cookie"},
        )
    user = AuthRepository(conn).get_session_user(hash_token(token))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
            headers={"WWW-Authenticate": "Cookie"},
        )
    return user


def build_session_expiry() -> tuple[str, int]:
    """返回 expires_at（本地时间字符串）与 Cookie 有效期秒数。"""
    seconds = settings.session_days * 24 * 3600
    expires = datetime.now() + timedelta(seconds=seconds)
    return expires.strftime("%Y-%m-%d %H:%M:%S"), seconds
