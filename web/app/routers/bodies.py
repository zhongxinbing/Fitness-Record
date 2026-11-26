"""体重记录 API 路由。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from app.auth import current_user
from app.database import get_db
from app.models import BodyIn, BodyOut
from app.repository import BodyRepository

router = APIRouter(prefix="/api/bodies", tags=["body"])


@router.get("", response_model=list[BodyOut])
def list_bodies(
    conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> list[dict]:
    return BodyRepository(conn, user["id"]).list()


@router.post("", response_model=BodyOut, status_code=201)
def create_body(
    payload: BodyIn,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = BodyRepository(conn, user["id"])
    record = payload.model_dump()
    record["date"] = payload.date.isoformat()
    record_id = repo.create(record)
    return {"id": record_id, **record}


@router.delete("/{record_id}", status_code=204, response_class=Response)
def delete_body(
    record_id: int, conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> Response:
    if not BodyRepository(conn, user["id"]).delete(record_id):
        raise HTTPException(status_code=404, detail="记录不存在")
