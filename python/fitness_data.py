"""Local data and progress calculations for Fitness Record."""

from __future__ import annotations

import json
import math
import os
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _today() -> str:
    return date.today().isoformat()


def _valid_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as error:
        raise ValueError("日期请使用 YYYY-MM-DD 格式") from error
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError("日期请使用 YYYY-MM-DD 格式")
    return value


def _positive_int(value: Any, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}必须是正整数") from error
    if number <= 0 or str(number) != str(value).strip():
        raise ValueError(f"{label}必须是正整数")
    return number


def _weight(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("重量必须是有效数字") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError("重量不能小于 0")
    return number


def _exercise(value: dict[str, Any]) -> dict[str, Any]:
    name = str(value.get("name", "")).strip()
    if not name:
        raise ValueError("动作名称不能为空")
    return {
        "name": name,
        "sets": _positive_int(value.get("sets"), "组数"),
        "reps": _positive_int(value.get("reps"), "次数"),
        "weight": _weight(value.get("weight")),
    }


class FitnessStore:
    """Persist workouts, reusable plans, and body-weight entries as local JSON."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, Any] = {
            "version": 1,
            "plans": [],
            "workouts": [],
            "body_weights": [],
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError(f"无法读取本地健身数据：{error}") from error
            if (
                not isinstance(loaded, dict)
                or loaded.get("version") != 1
                or any(not isinstance(loaded.get(key), list) for key in ("plans", "workouts", "body_weights"))
            ):
                raise RuntimeError("本地数据格式不受支持，原文件已保留")
            self.data = loaded

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def add_workout(
        self,
        training_date: str,
        title: str,
        body_parts: list[str],
        exercises: list[dict[str, Any]],
        notes: str = "",
    ) -> dict[str, Any]:
        clean_title = str(title).strip()
        clean_parts = list(dict.fromkeys(str(part).strip() for part in body_parts if str(part).strip()))
        if not clean_title:
            raise ValueError("训练名称不能为空")
        if not clean_parts:
            raise ValueError("请至少选择一个训练部位")
        if not exercises:
            raise ValueError("请至少添加一个训练动作")
        record = {
            "id": uuid.uuid4().hex,
            "date": _valid_date(training_date),
            "title": clean_title,
            "body_parts": clean_parts,
            "exercises": [_exercise(item) for item in exercises],
            "notes": str(notes).strip(),
        }
        self.data["workouts"].append(record)
        self._save()
        return record

    def add_plan(
        self,
        title: str,
        body_parts: list[str],
        exercises: list[dict[str, Any]],
    ) -> dict[str, Any]:
        clean_title = str(title).strip()
        clean_parts = list(dict.fromkeys(str(part).strip() for part in body_parts if str(part).strip()))
        if not clean_title:
            raise ValueError("计划名称不能为空")
        if not clean_parts:
            raise ValueError("请至少选择一个训练部位")
        if not exercises:
            raise ValueError("请至少添加一个训练动作")
        plan = {
            "id": uuid.uuid4().hex,
            "title": clean_title,
            "body_parts": clean_parts,
            "exercises": [_exercise(item) for item in exercises],
        }
        self.data["plans"].append(plan)
        self._save()
        return plan

    def add_body_weight(self, entry_date: str, weight: Any, notes: str = "") -> dict[str, Any]:
        value = _weight(weight)
        if value <= 0:
            raise ValueError("体重必须大于 0")
        record = {
            "id": uuid.uuid4().hex,
            "date": _valid_date(entry_date),
            "weight": value,
            "notes": str(notes).strip(),
        }
        self.data["body_weights"].append(record)
        self._save()
        return record

    def delete(self, collection: str, record_id: str) -> None:
        if collection not in ("plans", "workouts", "body_weights"):
            raise ValueError("不支持删除此类记录")
        items = self.data[collection]
        remaining = [item for item in items if item.get("id") != record_id]
        if len(remaining) == len(items):
            raise KeyError("记录不存在")
        self.data[collection] = remaining
        self._save()

    def monthly_summary(self, month: str | None = None) -> dict[str, Any]:
        month = month or _today()[:7]
        workouts = [item for item in self.data["workouts"] if item.get("date", "").startswith(month)]
        parts: Counter[str] = Counter()
        for workout in workouts:
            parts.update(set(workout.get("body_parts", [])))
        return {"sessions": len(workouts), "body_parts": parts}

    def training_volume_trend(self, limit: int = 12) -> list[tuple[str, float]]:
        volume_by_date: defaultdict[str, float] = defaultdict(float)
        for workout in self.data["workouts"]:
            for exercise in workout.get("exercises", []):
                volume_by_date[workout["date"]] += (
                    float(exercise["sets"]) * float(exercise["reps"]) * float(exercise["weight"])
                )
        dates = sorted(volume_by_date)[-limit:]
        return [(item, volume_by_date[item]) for item in dates]

    def body_weight_trend(self, limit: int = 12) -> list[tuple[str, float]]:
        entries = sorted(
            self.data["body_weights"],
            key=lambda item: (item.get("date", ""), item.get("id", "")),
        )[-limit:]
        return [(item["date"], float(item["weight"])) for item in entries]

    def recent_workouts(self) -> list[dict[str, Any]]:
        return sorted(
            self.data["workouts"],
            key=lambda item: (item.get("date", ""), item.get("id", "")),
            reverse=True,
        )

    def recent_body_weights(self) -> list[dict[str, Any]]:
        return sorted(
            self.data["body_weights"],
            key=lambda item: (item.get("date", ""), item.get("id", "")),
            reverse=True,
        )
