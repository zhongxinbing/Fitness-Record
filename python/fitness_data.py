"""Local data and progress calculations for Fitness Record."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
import uuid
from copy import deepcopy
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


class FitnessStoreError(RuntimeError):
    """Raised when local fitness data cannot be read or safely persisted."""


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


def _valid_time(value: Any) -> str:
    if value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError("时间请使用 HH:MM 格式")
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as error:
        raise ValueError("时间请使用 HH:MM 格式") from error
    if parsed.strftime("%H:%M") != value:
        raise ValueError("时间请使用 HH:MM 格式")
    return value


def _positive_int(value: Any, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}必须是正整数") from error
    if number <= 0 or str(number) != str(value).strip():
        raise ValueError(f"{label}必须是正整数")
    return number


def _nonnegative_int(value: Any, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}必须是非负整数") from error
    if number < 0 or str(number) != str(value).strip():
        raise ValueError(f"{label}必须是非负整数")
    return number


def _weight(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("重量必须是有效数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("重量必须是有效数字") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError("重量不能小于 0")
    return number


def _exercise(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("动作数据格式无效")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("动作名称不能为空")
    name = name.strip()
    alternatives = value.get("alternatives", [])
    if not isinstance(alternatives, list):
        raise ValueError("备选动作格式无效")
    normalized_alternatives: list[str] = []
    for alternative in alternatives:
        if not isinstance(alternative, str) or not alternative.strip():
            raise ValueError("备选动作名称无效")
        alternative = alternative.strip()
        if alternative != name and alternative not in normalized_alternatives:
            normalized_alternatives.append(alternative)
    rest_seconds = _nonnegative_int(value.get("rest_seconds", 60), "休息时间")
    if rest_seconds > 3600:
        raise ValueError("休息时间不能超过 60 分钟")
    raw_set_log = value.get("set_log", [])
    if not isinstance(raw_set_log, list):
        raise ValueError("训练组数据格式无效")
    set_log: list[dict[str, Any]] = []
    for raw_set in raw_set_log:
        if not isinstance(raw_set, dict):
            raise ValueError("训练组数据格式无效")
        completed = raw_set.get("completed", False)
        if not isinstance(completed, bool):
            raise ValueError("训练组完成状态无效")
        set_log.append({
            "weight": _weight(raw_set.get("weight", value.get("weight"))),
            "reps": _positive_int(raw_set.get("reps", value.get("reps")), "次数"),
            "completed": completed,
        })
    return {
        "name": name,
        "sets": _positive_int(value.get("sets"), "组数"),
        "reps": _positive_int(value.get("reps"), "次数"),
        "weight": _weight(value.get("weight")),
        "rest_seconds": rest_seconds,
        "alternatives": normalized_alternatives,
        "set_log": set_log,
    }


def _set_log(exercise: dict[str, Any], completed: bool) -> list[dict[str, Any]]:
    if exercise["set_log"]:
        return exercise["set_log"]
    return [
        {
            "weight": exercise["weight"],
            "reps": exercise["reps"],
            "completed": completed,
        }
        for _ in range(exercise["sets"])
    ]


class FitnessStore:
    """Persist workouts, set logs, templates, rest days, and legacy weight entries."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, Any] = {
            "version": 2,
            "plans": [],
            "workouts": [],
            "body_weights": [],
            "rest_days": [],
        }
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise FitnessStoreError(f"无法读取本地健身数据；原文件已保留：{error}") from error
            try:
                self.data = self._validate_document(loaded)
            except (KeyError, TypeError, ValueError) as error:
                raise FitnessStoreError(f"本地健身数据无效；原文件已保留：{error}") from error

    @staticmethod
    def _validate_document(value: Any) -> dict[str, Any]:
        if (
            not isinstance(value, dict)
            or type(value.get("version")) is not int
            or value.get("version") not in (1, 2)
        ):
            raise ValueError("数据版本不受支持")
        for collection in ("plans", "workouts", "body_weights"):
            if not isinstance(value.get(collection), list):
                raise ValueError(f"{collection} 必须是列表")
        raw_rest_days = value.get("rest_days", [])
        if not isinstance(raw_rest_days, list):
            raise ValueError("rest_days 必须是列表")

        seen_ids: set[str] = set()

        def validate_id(item: dict[str, Any]) -> str:
            record_id = item.get("id")
            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError("记录 ID 缺失或无效")
            if record_id in seen_ids:
                raise ValueError("记录 ID 重复")
            seen_ids.add(record_id)
            return record_id

        def validate_parts(item: dict[str, Any]) -> list[str]:
            parts = item.get("body_parts")
            if not isinstance(parts, list) or not parts:
                raise ValueError("训练部位缺失或无效")
            if any(not isinstance(part, str) or not part.strip() for part in parts):
                raise ValueError("训练部位包含无效内容")
            return list(dict.fromkeys(part.strip() for part in parts))

        def validate_exercises(item: dict[str, Any]) -> list[dict[str, Any]]:
            exercises = item.get("exercises")
            if not isinstance(exercises, list) or not exercises:
                raise ValueError("训练动作缺失或无效")
            return [_exercise(exercise) for exercise in exercises]

        plans: list[dict[str, Any]] = []
        for raw in value["plans"]:
            if not isinstance(raw, dict):
                raise ValueError("计划记录格式无效")
            record_id = validate_id(raw)
            title = raw.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("计划名称缺失或无效")
            plans.append({
                **raw,
                "id": record_id,
                "title": title.strip(),
                "body_parts": validate_parts(raw),
                "exercises": validate_exercises(raw),
            })

        workouts: list[dict[str, Any]] = []
        for raw in value["workouts"]:
            if not isinstance(raw, dict):
                raise ValueError("训练记录格式无效")
            record_id = validate_id(raw)
            title = raw.get("title")
            notes = raw.get("notes", "")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("训练名称缺失或无效")
            if not isinstance(notes, str):
                raise ValueError("训练备注格式无效")
            finished = raw.get("finished", True)
            if not isinstance(finished, bool):
                raise ValueError("训练完成状态无效")
            exercises = validate_exercises(raw)
            started_at = raw.get("started_at")
            if started_at is not None and (
                isinstance(started_at, bool)
                or not isinstance(started_at, (int, float))
                or not math.isfinite(started_at)
                or started_at < 0
            ):
                raise ValueError("训练开始时间无效")
            duration_seconds = raw.get("duration_seconds")
            if duration_seconds is not None:
                duration_seconds = _nonnegative_int(duration_seconds, "训练时长")
            for exercise in exercises:
                exercise["set_log"] = _set_log(exercise, finished)
            normalized_workout = {
                **raw,
                "id": record_id,
                "date": _valid_date(raw.get("date")),
                "training_time": _valid_time(raw.get("training_time", "")),
                "title": title.strip(),
                "body_parts": validate_parts(raw),
                "exercises": exercises,
                "notes": notes,
                "finished": finished,
            }
            if started_at is not None:
                normalized_workout["started_at"] = float(started_at)
            if duration_seconds is not None:
                normalized_workout["duration_seconds"] = duration_seconds
            workouts.append(normalized_workout)

        body_weights: list[dict[str, Any]] = []
        for raw in value["body_weights"]:
            if not isinstance(raw, dict):
                raise ValueError("体重记录格式无效")
            record_id = validate_id(raw)
            notes = raw.get("notes", "")
            if not isinstance(notes, str):
                raise ValueError("体重备注格式无效")
            weight = _weight(raw.get("weight"))
            if weight <= 0:
                raise ValueError("体重必须大于 0")
            body_weights.append({
                **raw,
                "id": record_id,
                "date": _valid_date(raw.get("date")),
                "weight": weight,
                "notes": notes,
            })

        rest_days: list[dict[str, Any]] = []
        for raw in raw_rest_days:
            if not isinstance(raw, dict):
                raise ValueError("休息日记录格式无效")
            record_id = validate_id(raw)
            rest_days.append({
                **raw,
                "id": record_id,
                "date": _valid_date(raw.get("date")),
            })

        return {
            "version": 2,
            "plans": plans,
            "workouts": workouts,
            "body_weights": body_weights,
            "rest_days": rest_days,
        }

    def _save(self, updated_data: dict[str, Any]) -> None:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(updated_data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise FitnessStoreError(f"无法安全保存本地健身数据：{error}") from error
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning("Could not remove temporary fitness data file %s", temporary, exc_info=True)
        self.data = updated_data

    def add_workout(
        self,
        training_date: str,
        title: str,
        body_parts: list[str],
        exercises: list[dict[str, Any]],
        notes: str = "",
        training_time: str | None = None,
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
            "training_time": _valid_time(
                training_time if training_time is not None else datetime.now().strftime("%H:%M")
            ),
            "title": clean_title,
            "body_parts": clean_parts,
            "exercises": [
                {**item, "set_log": _set_log(item, True)}
                for item in (_exercise(value) for value in exercises)
            ],
            "notes": str(notes).strip(),
            "finished": True,
        }
        updated_data = deepcopy(self.data)
        updated_data["workouts"].append(record)
        self._save(updated_data)
        return record

    def active_workout(self, training_date: str) -> dict[str, Any] | None:
        clean_date = _valid_date(training_date)
        active = [
            item for item in self.data["workouts"]
            if item["date"] == clean_date and not item["finished"]
        ]
        return max(
            active,
            key=lambda item: (item.get("training_time", ""), item["id"]),
            default=None,
        )

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
        updated_data = deepcopy(self.data)
        updated_data["plans"].append(plan)
        self._save(updated_data)
        return plan

    def add_daily_exercise(
        self,
        training_date: str,
        body_part: str,
        exercise: dict[str, Any],
    ) -> dict[str, Any]:
        return self.add_daily_exercises(training_date, body_part, [exercise])

    def add_daily_exercises(
        self,
        training_date: str,
        body_part: str | list[str],
        exercises: list[dict[str, Any]],
    ) -> dict[str, Any]:
        clean_date = _valid_date(training_date)
        raw_parts = body_part if isinstance(body_part, list) else [body_part]
        clean_parts = list(dict.fromkeys(
            str(part).strip() for part in raw_parts if str(part).strip()
        ))
        if not clean_parts:
            raise ValueError("请先选择训练部位")
        if not exercises:
            raise ValueError("请至少添加一个训练动作")
        normalized_exercises = [
            {**item, "set_log": _set_log(item, False)}
            for item in (_exercise(value) for value in exercises)
        ]
        updated_data = deepcopy(self.data)
        rest_days = [
            item for item in updated_data["rest_days"] if item["date"] != clean_date
        ]
        daily_workouts = sorted(
            (
                item for item in updated_data["workouts"]
                if item["date"] == clean_date and not item["finished"]
            ),
            key=lambda item: (item.get("training_time", ""), item["id"]),
        )
        if daily_workouts:
            workout = daily_workouts[-1]
            workout["body_parts"] = list(dict.fromkeys(
                [*workout["body_parts"], *clean_parts]
            ))
            workout["exercises"].extend(normalized_exercises)
        else:
            workout = {
                "id": uuid.uuid4().hex,
                "date": clean_date,
                "training_time": datetime.now().strftime("%H:%M"),
                "started_at": time.time(),
                "title": "今日训练",
                "body_parts": clean_parts,
                "exercises": normalized_exercises,
                "notes": "",
                "finished": False,
            }
            updated_data["workouts"].append(workout)
        updated_data["rest_days"] = rest_days
        self._save(updated_data)
        return workout

    def update_workout_details(
        self,
        workout_id: str,
        title: str,
        notes: str,
    ) -> None:
        clean_title = str(title).strip()
        clean_notes = str(notes).strip()
        if not clean_title:
            raise ValueError("训练名称不能为空")
        if len(clean_title) > 80:
            raise ValueError("训练名称不能超过 80 个字符")
        if len(clean_notes) > 1000:
            raise ValueError("训练备注不能超过 1000 个字符")
        updated_data = deepcopy(self.data)
        workout = next(
            (item for item in updated_data["workouts"] if item["id"] == workout_id),
            None,
        )
        if workout is None:
            raise KeyError("训练记录不存在")
        workout["title"] = clean_title
        workout["notes"] = clean_notes
        self._save(updated_data)

    def replace_workout_exercise(
        self,
        workout_id: str,
        index: int,
        exercise: dict[str, Any],
    ) -> None:
        normalized = _exercise(exercise)
        normalized["set_log"] = _set_log(normalized, False)
        updated_data = deepcopy(self.data)
        workout = next(
            (item for item in updated_data["workouts"] if item["id"] == workout_id),
            None,
        )
        if workout is None or not 0 <= index < len(workout["exercises"]):
            raise KeyError("训练动作不存在")
        previous = workout["exercises"][index]
        previous_sets = _set_log(previous, bool(workout.get("finished")))
        preserved_sets = [
            dict(entry) for entry in previous_sets[:normalized["sets"]]
        ]
        while len(preserved_sets) < normalized["sets"]:
            preserved_sets.append({
                "weight": normalized["weight"],
                "reps": normalized["reps"],
                "completed": False,
            })
        normalized["set_log"] = preserved_sets
        normalized["sets"] = len(preserved_sets)
        workout["exercises"][index] = normalized
        self._save(updated_data)

    def update_workout_set(
        self,
        workout_id: str,
        exercise_index: int,
        set_index: int,
        *,
        weight: Any | None = None,
        reps: Any | None = None,
        completed: bool | None = None,
    ) -> None:
        updated_data = deepcopy(self.data)
        workout = next(
            (item for item in updated_data["workouts"] if item["id"] == workout_id),
            None,
        )
        if workout is None or not 0 <= exercise_index < len(workout["exercises"]):
            raise KeyError("训练动作不存在")
        exercise = workout["exercises"][exercise_index]
        exercise["set_log"] = _set_log(exercise, bool(workout.get("finished")))
        if not 0 <= set_index < len(exercise["set_log"]):
            raise KeyError("训练组不存在")
        entry = exercise["set_log"][set_index]
        if weight is not None:
            entry["weight"] = _weight(weight)
        if reps is not None:
            entry["reps"] = _positive_int(reps, "次数")
        if completed is not None:
            if not isinstance(completed, bool):
                raise ValueError("训练组完成状态无效")
            entry["completed"] = completed
        exercise["sets"] = len(exercise["set_log"])
        exercise["weight"] = sum(item["weight"] for item in exercise["set_log"]) / len(
            exercise["set_log"]
        )
        exercise["reps"] = round(
            sum(item["reps"] for item in exercise["set_log"]) / len(exercise["set_log"])
        )
        self._save(updated_data)

    def add_workout_set(self, workout_id: str, exercise_index: int) -> None:
        updated_data = deepcopy(self.data)
        workout = next(
            (item for item in updated_data["workouts"] if item["id"] == workout_id),
            None,
        )
        if workout is None or not 0 <= exercise_index < len(workout["exercises"]):
            raise KeyError("训练动作不存在")
        exercise = workout["exercises"][exercise_index]
        exercise["set_log"] = _set_log(exercise, bool(workout.get("finished")))
        if len(exercise["set_log"]) >= 100:
            raise ValueError("单个动作最多记录 100 组")
        previous = exercise["set_log"][-1]
        exercise["set_log"].append({
            "weight": previous["weight"],
            "reps": previous["reps"],
            "completed": False,
        })
        exercise["sets"] = len(exercise["set_log"])
        self._save(updated_data)

    def finish_workout(self, training_date: str) -> dict[str, Any] | None:
        clean_date = _valid_date(training_date)
        updated_data = deepcopy(self.data)
        active = sorted(
            (
                item for item in updated_data["workouts"]
                if item["date"] == clean_date and not item["finished"]
            ),
            key=lambda item: (item.get("training_time", ""), item["id"]),
        )
        if not active:
            return None
        workout = active[-1]
        started_at = workout.get("started_at")
        if isinstance(started_at, (int, float)) and not isinstance(started_at, bool):
            workout["duration_seconds"] = max(0, int(time.time() - started_at))
        for exercise in workout["exercises"]:
            exercise["set_log"] = _set_log(exercise, False)
        workout["finished"] = True
        self._save(updated_data)
        return workout

    def remove_workout_exercise(self, workout_id: str, index: int) -> None:
        updated_data = deepcopy(self.data)
        workout = next(
            (item for item in updated_data["workouts"] if item["id"] == workout_id),
            None,
        )
        if workout is None or not 0 <= index < len(workout["exercises"]):
            raise KeyError("训练动作不存在")
        if len(workout["exercises"]) == 1:
            updated_data["workouts"] = [
                item for item in updated_data["workouts"] if item["id"] != workout_id
            ]
        else:
            workout["exercises"].pop(index)
        self._save(updated_data)

    def set_rest_day(self, entry_date: str, is_rest_day: bool) -> None:
        clean_date = _valid_date(entry_date)
        updated_data = deepcopy(self.data)
        if is_rest_day and any(
            item["date"] == clean_date for item in updated_data["workouts"]
        ):
            raise ValueError("当天已有训练记录，不能标记为休息日")
        existing = [
            item for item in updated_data["rest_days"] if item["date"] == clean_date
        ]
        if is_rest_day and not existing:
            updated_data["rest_days"].append({
                "id": uuid.uuid4().hex,
                "date": clean_date,
            })
        elif not is_rest_day:
            updated_data["rest_days"] = [
                item for item in updated_data["rest_days"] if item["date"] != clean_date
            ]
        self._save(updated_data)

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
        updated_data = deepcopy(self.data)
        updated_data["body_weights"].append(record)
        self._save(updated_data)
        return record

    def replace_exercises(
        self,
        collection: str,
        record_id: str,
        exercises: list[dict[str, Any]],
    ) -> None:
        if collection not in ("plans", "workouts"):
            raise ValueError("不支持修改此类记录的动作")
        if not exercises:
            raise ValueError("至少需要保留一个训练动作")
        normalized = [_exercise(item) for item in exercises]
        updated_data = deepcopy(self.data)
        record = next(
            (item for item in updated_data[collection] if item.get("id") == record_id),
            None,
        )
        if record is None:
            raise KeyError("记录不存在")
        record["exercises"] = normalized
        self._save(updated_data)

    def delete(self, collection: str, record_id: str) -> None:
        if collection not in ("plans", "workouts", "body_weights", "rest_days"):
            raise ValueError("不支持删除此类记录")
        updated_data = deepcopy(self.data)
        items = updated_data[collection]
        remaining = [item for item in items if item.get("id") != record_id]
        if len(remaining) == len(items):
            raise KeyError("记录不存在")
        updated_data[collection] = remaining
        self._save(updated_data)

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
            key=lambda item: (
                item.get("date", ""),
                item.get("training_time", ""),
                item.get("id", ""),
            ),
            reverse=True,
        )

    def recent_body_weights(self) -> list[dict[str, Any]]:
        return sorted(
            self.data["body_weights"],
            key=lambda item: (item.get("date", ""), item.get("id", "")),
            reverse=True,
        )

    def calendar_summary(self, month: str) -> dict[str, dict[str, Any]]:
        if len(month) != 7:
            raise ValueError("月份请使用 YYYY-MM 格式")
        try:
            datetime.strptime(month, "%Y-%m")
        except ValueError as error:
            raise ValueError("月份请使用 YYYY-MM 格式") from error
        result: dict[str, dict[str, Any]] = {}
        for workout in self.data["workouts"]:
            if workout["date"].startswith(month):
                entry = result.setdefault(
                    workout["date"],
                    {"workouts": [], "body_parts": []},
                )
                entry["workouts"].append(workout)
                entry["body_parts"] = list(dict.fromkeys(
                    [*entry["body_parts"], *workout["body_parts"]]
                ))
        for rest_day in self.data["rest_days"]:
            if rest_day["date"].startswith(month):
                result.setdefault(
                    rest_day["date"],
                    {"workouts": [], "body_parts": []},
                )["is_rest_day"] = True
        return result

    def personal_records(self) -> list[dict[str, Any]]:
        records: dict[str, dict[str, Any]] = {}
        for workout in self.data["workouts"]:
            for exercise in workout["exercises"]:
                name = exercise["name"]
                current = records.get(name)
                set_weights = [
                    float(entry["weight"])
                    for entry in exercise.get("set_log", [])
                    if entry["completed"]
                ]
                if not set_weights and not exercise.get("set_log"):
                    set_weights = [float(exercise["weight"])]
                if not set_weights:
                    continue
                weight = max(set_weights)
                if current is None or weight > current["weight"] or (
                    weight == current["weight"] and workout["date"] > current["date"]
                ):
                    records[name] = {"name": name, "weight": weight, "date": workout["date"]}
        return sorted(
            records.values(),
            key=lambda item: (item["weight"], item["name"]),
            reverse=True,
        )
