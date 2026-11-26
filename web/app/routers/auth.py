"""注册 / 登录 / 登出 / 当前用户 API。"""
from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import build_session_expiry, current_user
from app.config import settings
from app.database import get_db
from app.models import AuthOut, LoginIn, RegisterIn, UserOut
from app.repository import AuthRepository
from app.security import (
    SESSION_COOKIE,
    hash_password,
    hash_token,
    new_session_token,
    throttle,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger("fitness.auth")


def _set_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _issue_session(conn: sqlite3.Connection, user_id: int, response: Response) -> None:
    token = new_session_token()
    expires_at, max_age = build_session_expiry()
    repo = AuthRepository(conn)
    repo.purge_expired_sessions()
    repo.create_session(user_id, hash_token(token), expires_at)
    _set_cookie(response, token, max_age)


@router.post("/register", response_model=AuthOut, status_code=201, summary="注册并自动登录")
def register(payload: RegisterIn, response: Response, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    repo = AuthRepository(conn)
    if repo.get_user(payload.username) is not None:
        raise HTTPException(status_code=409, detail="该用户名已被占用")

    # 首个注册用户：认领旧版单机数据，避免历史记录丢失
    is_first_user = repo.count_users() == 0
    try:
        user_id = repo.create_user(payload.username, hash_password(payload.password))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="该用户名已被占用")

    adopted = repo.adopt_legacy_data(user_id) if is_first_user else False

    _issue_session(conn, user_id, response)
    logger.info("新用户注册成功: %s (id=%s, 认领旧数据=%s)", payload.username, user_id, adopted)
    return {"user": {"id": user_id, "username": payload.username}, "adopted_legacy": adopted}


@router.post("/login", response_model=AuthOut, summary="登录")
def login(payload: LoginIn, response: Response, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if throttle.is_locked(payload.username):
        raise HTTPException(status_code=429, detail="尝试次数过多，请 1 分钟后再试")

    repo = AuthRepository(conn)
    user = repo.get_user(payload.username)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        throttle.register_failure(payload.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    throttle.reset(payload.username)
    _issue_session(conn, user["id"], response)
    return {"user": {"id": user["id"], "username": user["username"]}, "adopted_legacy": False}


@router.post("/logout", status_code=204, response_class=Response, summary="退出登录")
def logout(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        AuthRepository(conn).delete_session(hash_token(token))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut, summary="当前登录用户")
def me(user: dict = Depends(current_user)) -> dict:
    return user
