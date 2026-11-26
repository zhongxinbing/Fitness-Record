"""训练计划 API 路由。

计划状态流转：planned（今日计划）→ 打卡 complete → done（进入历史）。
"""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.auth import current_user
from app.config import local_today
from app.database import get_db
from app.models import (
    BODY_PARTS,
    ExerciseNameOut,
    ExerciseProgressOut,
    HistoryDayOut,
    PlanExerciseIn,
    PlanExerciseOut,
    PlanExercisePatch,
    PlanIn,
    PlanOut,
    PlanPatch,
    SetLogIn,
    SetLogOut,
    WeeklyOut,
)
from app.repository import PlanRepository

router = APIRouter(prefix="/api", tags=["plans"])


def _repo(conn: sqlite3.Connection, user: dict) -> PlanRepository:
    """按当前登录用户构造仓储，所有查询天然带 user_id 过滤。"""
    return PlanRepository(conn, user["id"])


def _require(plan: Optional[dict]) -> dict:
    if plan is None:
        raise HTTPException(status_code=404, detail="计划不存在")
    return plan


@router.get("/body-parts", summary="可选训练部位白名单")
def body_parts() -> dict:
    return {"body_parts": list(BODY_PARTS)}


@router.get("/plans", response_model=list[PlanOut], summary="按日期/状态查询计划")
def list_plans(
    plan_date: Optional[date] = Query(None, description="计划日期，不传则返回全部"),
    status: Optional[str] = Query(None, pattern="^(planned|done)$"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[dict]:
    return _repo(conn, user).list(plan_date=plan_date, status=status)


@router.get("/plans/others", response_model=list[PlanOut], summary="非今日的待完成计划")
def list_other_plans(
    conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> list[dict]:
    return _repo(conn, user).list_others(local_today())


@router.post("/plans", response_model=PlanOut, status_code=201, summary="新建训练计划（可多部位多动作）")
def create_plan(
    payload: PlanIn,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = _repo(conn, user)
    plan_id = repo.create({
        "plan_date": payload.plan_date.isoformat(),
        "body_parts": payload.body_parts,
        "title": payload.title,
        "note": payload.note,
        "exercises": [e.model_dump() for e in payload.exercises],
    })
    return _require(repo.get(plan_id))


@router.patch("/plans/{plan_id}", response_model=PlanOut, summary="修改计划本身（日期/主题/部位/备注）")
def patch_plan(
    plan_id: int,
    payload: PlanPatch,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")
    fields = payload.model_dump(exclude_none=True)
    if "plan_date" in fields:
        fields["plan_date"] = fields["plan_date"].isoformat()
    if not repo.update_plan(plan_id, fields):
        raise HTTPException(status_code=422, detail="没有可更新的字段")
    return _require(repo.get(plan_id))


@router.put(
    "/plans/{plan_id}/exercises/{exercise_id}/sets/{set_index}",
    response_model=SetLogOut,
    summary="勾选/取消某一组，并记录实际次数与重量",
)
def log_exercise_set(
    plan_id: int,
    exercise_id: int,
    set_index: int,
    payload: SetLogIn,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")
    result = repo.log_set(
        plan_id, exercise_id, set_index, payload.done, payload.reps, payload.weight, payload.rpe
    )
    if result is None:
        raise HTTPException(status_code=404, detail="动作不存在，或组序号超出该动作的计划组数")
    return result


@router.post(
    "/plans/{plan_id}/exercises/{exercise_id}/skip",
    response_model=PlanOut,
    summary="训练中跳过/恢复某个动作",
)
def skip_exercise(
    plan_id: int,
    exercise_id: int,
    skip: bool = Query(True, description="true=跳过，false=恢复"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")
    cleared = repo.set_skipped(plan_id, exercise_id, skip)
    if cleared is None:
        raise HTTPException(status_code=404, detail="动作不存在或不属于该计划")
    return _require(repo.get(plan_id))


@router.post(
    "/plans/{plan_id}/copy",
    response_model=PlanOut,
    status_code=201,
    summary="从历史复制该计划到指定日期（默认今天）",
)
def copy_plan(
    plan_id: int,
    plan_date: Optional[date] = Query(None, description="复制后落地的日期，缺省为今天"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")
    target_date = (plan_date or local_today()).isoformat()
    new_id = repo.copy_from(plan_id, target_date)
    if new_id is None:
        raise HTTPException(status_code=404, detail="计划不存在")
    return _require(repo.get(new_id))


@router.get("/plans/{plan_id}", response_model=PlanOut, summary="计划详情")
def get_plan(
    plan_id: int, conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> dict:
    return _require(_repo(conn, user).get(plan_id))


@router.post("/plans/{plan_id}/complete", response_model=PlanOut, summary="打卡完成，转入历史")
def complete_plan(
    plan_id: int, conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")
    if not repo.complete(plan_id):
        raise HTTPException(status_code=409, detail="该计划已完成，无需重复打卡")
    return _require(repo.get(plan_id))


@router.post("/plans/{plan_id}/reopen", response_model=PlanOut, summary="撤销打卡，退回计划")
def reopen_plan(
    plan_id: int, conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")
    if not repo.reopen(plan_id):
        raise HTTPException(status_code=409, detail="该计划尚未完成")
    return _require(repo.get(plan_id))


@router.post(
    "/plans/{plan_id}/exercises",
    response_model=PlanExerciseOut,
    status_code=201,
    summary="向计划追加一个动作",
)
def add_plan_exercise(
    plan_id: int,
    payload: PlanExerciseIn,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")
    ex = payload.model_dump()
    ex_id = repo.add_exercise(plan_id, ex)
    plan = _require(repo.get(plan_id))
    created = next((e for e in plan["exercises"] if e["id"] == ex_id), None)
    if created is None:
        raise HTTPException(status_code=500, detail="动作添加失败")
    return created


@router.patch(
    "/plans/{plan_id}/exercises/{exercise_id}",
    response_model=PlanExerciseOut,
    summary="局部修改动作（休息时长等）",
)
def patch_plan_exercise(
    plan_id: int,
    exercise_id: int,
    payload: PlanExercisePatch,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    repo = _repo(conn, user)
    if not repo.exists(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")

    fields = payload.model_dump(exclude_none=True)
    # 改名时保持“同一计划内动作名不重复”的约束
    if "name" in fields:
        plan = _require(repo.get(plan_id))
        if any(e["id"] != exercise_id and e["name"] == fields["name"] for e in plan["exercises"]):
            raise HTTPException(status_code=409, detail="同一计划内动作名称不能重复")

    if not repo.update_exercise(plan_id, exercise_id, fields):
        raise HTTPException(status_code=404, detail="动作不存在")
    plan = _require(repo.get(plan_id))
    updated = next((e for e in plan["exercises"] if e["id"] == exercise_id), None)
    if updated is None:
        raise HTTPException(status_code=500, detail="动作更新失败")
    return updated


@router.delete(
    "/plans/{plan_id}/exercises/{exercise_id}",
    status_code=204,
    response_class=Response,
    summary="删除计划内某个动作",
)
def delete_plan_exercise(
    plan_id: int,
    exercise_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> Response:
    if not _repo(conn, user).delete_exercise(plan_id, exercise_id):
        raise HTTPException(status_code=404, detail="动作不存在")


@router.delete("/plans/{plan_id}", status_code=204, response_class=Response, summary="删除计划")
def delete_plan(
    plan_id: int, conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> Response:
    if not _repo(conn, user).delete(plan_id):
        raise HTTPException(status_code=404, detail="计划不存在")


@router.get("/history", response_model=list[HistoryDayOut], summary="历史记录（按天聚合，含部位）")
def history(
    conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> list[dict]:
    return _repo(conn, user).history()


@router.get(
    "/progress/exercise-names",
    response_model=list[ExerciseNameOut],
    summary="可选动作名列表（用于进步曲线筛选与输入联想）",
)
def exercise_names(
    conn: sqlite3.Connection = Depends(get_db), user: dict = Depends(current_user)
) -> list[dict]:
    return _repo(conn, user).exercise_names()


@router.get(
    "/progress/exercise",
    response_model=ExerciseProgressOut,
    summary="单个动作的进步曲线（按天聚合，含 PR 与估算 1RM）",
)
def exercise_progress(
    name: str = Query(..., min_length=1, max_length=50, description="动作名称，需与计划中完全一致"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    data = _repo(conn, user).exercise_progress(name.strip())
    if data is None:
        raise HTTPException(status_code=404, detail="还没有这个动作的历史记录")
    return data


@router.get("/weekly", response_model=WeeklyOut, summary="周视图：每周训练容量与体重")
def weekly(
    weeks: int = Query(8, ge=1, le=52, description="回看几周，含本周"),
    conn: sqlite3.Connection = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    return _repo(conn, user).weekly(weeks)
