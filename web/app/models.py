"""数据模型与请求/响应 Schema。

核心结构：
  PlanIn / PlanOut —— 一次训练计划：可包含多个部位（body_parts）与多个动作（exercises）
  打卡（complete）后 status 变为 done，进入历史
"""
from __future__ import annotations

from datetime import date as date_type
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import local_today

# 允许的训练部位白名单：前端 chips 与后端校验共用。
BODY_PARTS = ("胸", "背", "腿", "肩", "臂", "核心", "有氧", "全身", "其他")
MAX_PARTS = 5
MAX_EXERCISES = 20


# ---------------- 账号 ----------------

class RegisterIn(BaseModel):
    """注册入参。"""

    username: str = Field(..., min_length=2, max_length=20, description="用户名 2–20 位，字母/数字/下划线/中文")
    password: str = Field(..., min_length=8, max_length=128, description="密码至少 8 位")

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fa5]{2,20}", value):
            raise ValueError("用户名只能包含字母、数字、下划线或中文，长度 2–20")
        return value


class LoginIn(BaseModel):
    """登录入参。"""

    username: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    """当前会话用户。"""

    id: int
    username: str


class AuthOut(BaseModel):
    """注册/登录返回体。"""

    user: UserOut
    adopted_legacy: bool = Field(False, description="是否认领了旧版单机数据")


class PlanExerciseIn(BaseModel):
    """计划内单个动作。"""

    name: str = Field(..., min_length=1, max_length=50, description="动作名称")
    sets: int = Field(3, ge=1, le=99, description="计划组数")
    reps: int = Field(10, ge=1, le=999, description="计划次数")
    weight: float = Field(0.0, ge=0, le=1000, description="计划重量 kg，自重填 0")
    rest_seconds: int = Field(90, ge=1, le=600, description="每组间休息秒数，用户自定义")

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("动作名称不能为空")
        return value


class SetLogIn(BaseModel):
    """单组完成记录入参。"""

    done: bool = Field(True, description="true=勾选完成，false=取消")
    reps: Optional[int] = Field(None, ge=0, le=999, description="实际次数，缺省沿用计划值")
    weight: Optional[float] = Field(None, ge=0, le=1000, description="实际重量，缺省沿用计划值")
    rpe: Optional[float] = Field(None, ge=1, le=10, description="主观强度 RPE 1–10（0.5 步进）")

    @field_validator("rpe")
    @classmethod
    def _half_step(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if abs(value * 2 - round(value * 2)) > 1e-9:
            raise ValueError("RPE 需为 0.5 的整数倍")
        return round(value, 1)


class SetLogOut(BaseModel):
    set_index: int
    reps: Optional[int] = None
    weight: Optional[float] = None
    rpe: Optional[float] = None


class PlanExerciseOut(PlanExerciseIn):
    id: int
    sort_order: int
    volume: float = Field(description="计划容量 = 组数 × 次数 × 重量")
    done_sets: list[SetLogOut] = Field(default_factory=list, description="已完成的组（实际次数/重量）")
    done_count: int = Field(0, description="已完成组数")
    actual_volume: float = Field(0, description="已完成组的实际容量")
    skipped: bool = Field(False, description="训练中跳过该动作（不计入必做组数）")
    avg_rpe: Optional[float] = Field(None, description="已完成组的平均 RPE")


class PlanExercisePatch(BaseModel):
    """动作局部更新：只改传入的字段（用于调整休息时长等）。"""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    sets: Optional[int] = Field(None, ge=1, le=99)
    reps: Optional[int] = Field(None, ge=1, le=999)
    weight: Optional[float] = Field(None, ge=0, le=1000)
    rest_seconds: Optional[int] = Field(None, ge=1, le=600)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("动作名称不能为空")
        return value

    @model_validator(mode="after")
    def _at_least_one(self) -> "PlanExercisePatch":
        if not self.model_dump(exclude_none=True):
            raise ValueError("至少需要提供一个待更新字段")
        return self


class PlanIn(BaseModel):
    """新建计划入参。"""

    plan_date: date_type = Field(default_factory=local_today, description="计划日期，默认今天")
    body_parts: list[str] = Field(..., min_length=1, max_length=MAX_PARTS, description="训练部位，可多个")
    title: str = Field("", max_length=50, description="计划主题，如 推日")
    note: str = Field("", max_length=200, description="备注")
    exercises: list[PlanExerciseIn] = Field(..., min_length=1, max_length=MAX_EXERCISES)

    @field_validator("body_parts")
    @classmethod
    def _check_parts(cls, value: list[str]) -> list[str]:
        invalid = [v for v in value if v not in BODY_PARTS]
        if invalid:
            raise ValueError(f"部位不合法: {', '.join(invalid)}；允许 {', '.join(BODY_PARTS)}")
        # 去重并保持顺序
        return list(dict.fromkeys(value))

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _unique_names(self) -> "PlanIn":
        names = [e.name for e in self.exercises]
        if len(set(names)) != len(names):
            raise ValueError("同一个计划内动作名称不能重复")
        return self


class PlanPatch(BaseModel):
    """计划整体局部更新：日期 / 主题 / 部位 / 备注。"""

    plan_date: Optional[date_type] = None
    body_parts: Optional[list[str]] = Field(None, min_length=1, max_length=MAX_PARTS)
    title: Optional[str] = Field(None, max_length=50)
    note: Optional[str] = Field(None, max_length=200)

    @field_validator("body_parts")
    @classmethod
    def _check_parts(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        invalid = [v for v in value if v not in BODY_PARTS]
        if invalid:
            raise ValueError(f"部位不合法: {', '.join(invalid)}")
        return list(dict.fromkeys(value))

    @field_validator("title", "note")
    @classmethod
    def _strip_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def _at_least_one(self) -> "PlanPatch":
        if not self.model_dump(exclude_none=True):
            raise ValueError("至少需要提供一个待更新字段")
        return self


class PlanOut(BaseModel):
    """计划出参。"""

    id: int
    plan_date: date_type
    body_parts: list[str]
    title: str
    note: str
    status: Literal["planned", "done"]
    completed_at: Optional[str] = None
    exercises: list[PlanExerciseOut]
    exercise_count: int
    total_sets: int
    total_volume: float
    done_set_count: int = 0
    total_set_count: int = 0
    actual_volume: float = 0


class HistoryDayOut(BaseModel):
    """历史某一天：当天完成的计划与涉及部位。"""

    date: date_type
    body_parts: list[str] = Field(description="当天训练过的部位（去重）")
    plan_count: int
    exercise_count: int
    total_sets: int
    total_volume: float
    plans: list[PlanOut]


class StatsOut(BaseModel):
    """历史页顶部概览。"""

    total_plans: int = Field(description="累计计划数")
    done_plans: int = Field(description="累计完成次数")
    week_sessions: int = Field(description="本周完成次数")
    total_sets: int = Field(description="累计组数")
    total_volume: float = Field(description="累计容量 kg")
    latest_weight: Optional[float] = Field(default=None, description="最新体重 kg")
    body_part_dist: dict[str, int] = Field(default_factory=dict, description="部位训练次数")


class BodyIn(BaseModel):
    """体重记录入参（接口保留）。"""

    date: date_type = Field(default_factory=local_today)
    weight: float = Field(..., ge=20, le=500)
    body_fat: Optional[float] = Field(None, ge=2, le=70)
    note: str = Field("", max_length=200)


class BodyOut(BodyIn):
    id: int


class ExerciseNameOut(BaseModel):
    """可选动作名（来自历史与在练计划），用于筛选与联想。"""

    name: str
    session_count: int
    last_date: Optional[str] = None


class ProgressPoint(BaseModel):
    date: date_type
    max_weight: float
    volume: float
    sets: int
    est_1rm: float
    avg_rpe: Optional[float] = None


class WeeklyPoint(BaseModel):
    """一周（周一至周日）的汇总。"""

    week_start: date_type
    sessions: int = Field(0, description="该周完成打卡的计划数")
    volume: float = Field(0, description="该周总训练容量 kg")
    sets: int = Field(0, description="该周记录的总组数")
    body_weight: Optional[float] = Field(None, description="该周最后一条体重记录")


class WeeklyOut(BaseModel):
    weeks: list[WeeklyPoint]
    avg_volume: float = 0
    avg_sessions: float = 0
    week_count: int = 0


class ExerciseProgressOut(BaseModel):
    """单个动作的进步曲线。"""

    name: str
    points: list[ProgressPoint]
    pr_weight: float
    pr_date: Optional[date_type] = None
    best_volume: float
    total_sets: int
    avg_rpe: Optional[float] = None
