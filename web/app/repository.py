"""数据访问层（Repository）。

所有业务表查询都按 user_id 隔离；SQL 集中在本模块，路由层只做参数校验与响应组装。
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Iterable, Optional


def _volume(sets: int, reps: int, weight: float) -> float:
    """计划容量：组数 × 次数 × 重量（自重动作重量为 0）。"""
    return round(float(sets) * float(reps) * float(weight), 2)


def _split_parts(raw: str) -> list[str]:
    return [p for p in raw.split(",") if p]


def _week_start(today: date) -> date:
    """本周起点（周一）。"""
    return today - timedelta(days=today.weekday())


class AuthRepository:
    """账号与会话仓储。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def count_users(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"])

    def get_user(self, username: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def create_user(self, username: str, password_hash: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash)
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def adopt_legacy_data(self, user_id: int) -> bool:
        """把历史单机数据（user_id = 0）归属给首个注册用户。"""
        plans = self.conn.execute(
            "UPDATE training_plans SET user_id = ? WHERE user_id = 0", (user_id,)
        ).rowcount
        bodies = self.conn.execute(
            "UPDATE body_records SET user_id = ? WHERE user_id = 0", (user_id,)
        ).rowcount
        self.conn.commit()
        return bool(plans or bodies)

    # ---- 会话 ----
    def create_session(self, user_id: int, token_hash: str, expires_at: str) -> None:
        self.conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )
        self.conn.commit()

    def get_session_user(self, token_hash: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT u.id, u.username FROM auth_sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > datetime('now', 'localtime')",
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token_hash: str) -> None:
        self.conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
        self.conn.commit()

    def purge_expired_sessions(self) -> int:
        cur = self.conn.execute(
            "DELETE FROM auth_sessions WHERE expires_at <= datetime('now', 'localtime')"
        )
        self.conn.commit()
        return cur.rowcount


class PlanRepository:
    """训练计划仓储（按用户隔离）。"""

    def __init__(self, conn: sqlite3.Connection, user_id: int) -> None:
        self.conn = conn
        self.user_id = user_id

    # ---------------- 查询 ----------------
    def list(self, plan_date: Optional[date] = None, status: Optional[str] = None) -> list[dict]:
        sql = "SELECT * FROM training_plans WHERE user_id = ?"
        params: list = [self.user_id]
        if plan_date is not None:
            sql += " AND plan_date = ?"
            params.append(plan_date.isoformat())
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY plan_date DESC, id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return self._attach_exercises(rows)

    def list_others(self, today: date) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM training_plans WHERE user_id = ? AND status = 'planned' AND plan_date <> ? "
            "ORDER BY plan_date ASC, id DESC",
            (self.user_id, today.isoformat()),
        ).fetchall()
        return self._attach_exercises(rows)

    def get(self, plan_id: int) -> Optional[dict]:
        rows = self.conn.execute(
            "SELECT * FROM training_plans WHERE id = ? AND user_id = ?", (plan_id, self.user_id)
        ).fetchall()
        if not rows:
            return None
        return self._attach_exercises(rows)[0]

    def exists(self, plan_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM training_plans WHERE id = ? AND user_id = ?", (plan_id, self.user_id)
        ).fetchone() is not None

    def _attach_exercises(self, plans: Iterable[sqlite3.Row]) -> list[dict]:
        rows = list(plans)
        if not rows:
            return []
        ids = [r["id"] for r in rows]
        ex_rows = self.conn.execute(
            "SELECT id, plan_id, name, sets, reps, weight, rest_seconds, note, sort_order "
            "FROM plan_exercises WHERE plan_id IN ({}) ORDER BY plan_id, sort_order, id".format(
                ",".join("?" * len(ids))
            ),
            ids,
        ).fetchall()

        # 每组完成记录（只取已完成，未完成不落库）
        ex_ids = [r["id"] for r in ex_rows]
        logged: dict[int, list[dict]] = {eid: [] for eid in ex_ids}
        if ex_ids:
            set_rows = self.conn.execute(
                "SELECT exercise_id, set_index, reps, weight FROM exercise_sets "
                "WHERE done = 1 AND exercise_id IN ({}) ORDER BY exercise_id, set_index".format(
                    ",".join("?" * len(ex_ids))
                ),
                ex_ids,
            ).fetchall()
            for sr in set_rows:
                logged[sr["exercise_id"]].append({
                    "set_index": sr["set_index"],
                    "reps": sr["reps"],
                    "weight": sr["weight"],
                })

        bucket: dict[int, list[dict]] = {pid: [] for pid in ids}
        for r in ex_rows:
            sets_done = logged.get(r["id"], [])
            actual_vol = round(sum((x["reps"] or 0) * (x["weight"] or 0) for x in sets_done), 2)
            item = {
                "id": r["id"],
                "name": r["name"],
                "sets": r["sets"],
                "reps": r["reps"],
                "weight": r["weight"],
                "rest_seconds": r["rest_seconds"],
                "sort_order": r["sort_order"],
                "volume": _volume(r["sets"], r["reps"], r["weight"]),
                "done_sets": sets_done,
                "done_count": len(sets_done),
                "actual_volume": actual_vol,
            }
            bucket[r["plan_id"]].append(item)

        result = []
        for r in rows:
            ex = bucket.get(r["id"], [])
            result.append({
                "id": r["id"],
                "plan_date": r["plan_date"],
                "body_parts": _split_parts(r["body_parts"]),
                "title": r["title"],
                "note": r["note"],
                "status": r["status"],
                "completed_at": r["completed_at"],
                "exercises": ex,
                "exercise_count": len(ex),
                "total_sets": sum(e["sets"] for e in ex),
                "total_volume": round(sum(e["volume"] for e in ex), 2),
                "done_set_count": sum(e["done_count"] for e in ex),
                "total_set_count": sum(e["sets"] for e in ex),
                "actual_volume": round(sum(e["actual_volume"] for e in ex), 2),
            })
        return result

    def history(self, limit_days: int = 120) -> list[dict]:
        """按天聚合已完成计划。"""
        rows = self.conn.execute(
            "SELECT * FROM training_plans WHERE user_id = ? AND status = 'done' "
            "ORDER BY plan_date DESC, id DESC",
            (self.user_id,),
        ).fetchall()
        plans = self._attach_exercises(rows)

        days: dict[str, dict] = {}
        for p in plans:
            d = p["plan_date"]
            day = days.setdefault(d, {
                "date": d,
                "body_parts": [],
                "plan_count": 0,
                "exercise_count": 0,
                "total_sets": 0,
                "total_volume": 0.0,
                "plans": [],
            })
            day["plans"].append(p)
            day["plan_count"] += 1
            day["exercise_count"] += p["exercise_count"]
            day["total_sets"] += p["total_sets"]
            day["total_volume"] = round(day["total_volume"] + p["total_volume"], 2)
            for part in p["body_parts"]:
                if part not in day["body_parts"]:
                    day["body_parts"].append(part)

        return sorted(days.values(), key=lambda x: x["date"], reverse=True)[:limit_days]

    # ---------------- 写入 ----------------
    def create(self, payload: dict) -> int:
        exercises: list[dict] = payload["exercises"]
        try:
            cur = self.conn.execute(
                "INSERT INTO training_plans (user_id, plan_date, body_parts, title, note, status) "
                "VALUES (?, ?, ?, ?, ?, 'planned')",
                (self.user_id, payload["plan_date"], ",".join(payload["body_parts"]),
                 payload["title"], payload["note"]),
            )
            plan_id = int(cur.lastrowid)
            for idx, e in enumerate(exercises):
                self.conn.execute(
                    "INSERT INTO plan_exercises (plan_id, name, sets, reps, weight, rest_seconds, note, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, '', ?)",
                    (plan_id, e["name"], e["sets"], e["reps"], e["weight"],
                     e.get("rest_seconds", 90), idx),
                )
            self.conn.commit()
            return plan_id
        except Exception:
            self.conn.rollback()
            raise

    def log_set(self, plan_id: int, exercise_id: int, set_index: int,
                done: bool, reps: Optional[int], weight: Optional[float]) -> Optional[dict]:
        """勾选/取消某一组：done=True 写入实际次数与重量，done=False 删除该组记录。"""
        row = self.conn.execute(
            "SELECT e.sets, e.reps, e.weight FROM plan_exercises e "
            "JOIN training_plans p ON p.id = e.plan_id "
            "WHERE e.id = ? AND e.plan_id = ? AND p.user_id = ?",
            (exercise_id, plan_id, self.user_id),
        ).fetchone()
        if row is None:
            return None
        if set_index < 1 or set_index > int(row["sets"]):
            return None

        if not done:
            self.conn.execute(
                "DELETE FROM exercise_sets WHERE exercise_id = ? AND set_index = ?",
                (exercise_id, set_index),
            )
            self.conn.commit()
            return {"set_index": set_index, "reps": None, "weight": None, "done": False}

        actual_reps = row["reps"] if reps is None else int(reps)
        actual_weight = row["weight"] if weight is None else float(weight)
        self.conn.execute(
            "INSERT INTO exercise_sets (exercise_id, set_index, done, reps, weight, done_at) "
            "VALUES (?, ?, 1, ?, ?, datetime('now', 'localtime')) "
            "ON CONFLICT(exercise_id, set_index) DO UPDATE SET "
            "done = 1, reps = excluded.reps, weight = excluded.weight, done_at = excluded.done_at",
            (exercise_id, set_index, actual_reps, actual_weight),
        )
        self.conn.commit()
        return {"set_index": set_index, "reps": actual_reps, "weight": actual_weight, "done": True}

    def update_plan(self, plan_id: int, fields: dict) -> bool:
        """更新计划本身的日期/部位/标题/备注。"""
        updates: dict = {}
        if fields.get("plan_date") is not None:
            updates["plan_date"] = fields["plan_date"]
        if fields.get("body_parts") is not None:
            updates["body_parts"] = ",".join(fields["body_parts"])
        if fields.get("title") is not None:
            updates["title"] = fields["title"]
        if fields.get("note") is not None:
            updates["note"] = fields["note"]
        if not updates:
            return False
        assignments = ", ".join(f"{k} = ?" for k in updates)
        cur = self.conn.execute(
            f"UPDATE training_plans SET {assignments} WHERE id = ? AND user_id = ?",
            [*updates.values(), plan_id, self.user_id],
        )
        self.conn.commit()
        return cur.rowcount > 0

    def exercise_names(self) -> list[dict]:
        """当前用户所有动作名（含计划中与历史），带出现次数和最近日期。"""
        rows = self.conn.execute(
            "SELECT e.name AS name, COUNT(DISTINCT p.id) AS n, MAX(p.plan_date) AS last_date "
            "FROM plan_exercises e JOIN training_plans p ON p.id = e.plan_id "
            "WHERE p.user_id = ? GROUP BY e.name "
            "ORDER BY n DESC, last_date DESC",
            (self.user_id,),
        ).fetchall()
        return [{"name": r["name"], "session_count": int(r["n"]), "last_date": r["last_date"]} for r in rows]

    def exercise_progress(self, name: str) -> Optional[dict]:
        """单个动作按天聚合的进步曲线：最大重量、容量、组数、估算 1RM。"""
        rows = self.conn.execute(
            "SELECT p.id AS pid, p.plan_date, e.id AS eid, e.sets, e.reps, e.weight "
            "FROM plan_exercises e JOIN training_plans p ON p.id = e.plan_id "
            "WHERE p.user_id = ? AND p.status = 'done' AND e.name = ? "
            "ORDER BY p.plan_date, p.id",
            (self.user_id, name),
        ).fetchall()
        if not rows:
            return None

        eids = [r["eid"] for r in rows]
        logged: dict[int, list] = {eid: [] for eid in eids}
        set_rows = self.conn.execute(
            "SELECT exercise_id, reps, weight FROM exercise_sets "
            "WHERE done = 1 AND exercise_id IN ({})".format(",".join("?" * len(eids))),
            eids,
        ).fetchall()
        for sr in set_rows:
            logged[sr["exercise_id"]].append(sr)

        buckets: dict[str, dict] = {}
        for r in rows:
            sets = logged.get(r["eid"], [])
            if sets:
                reps_list = [(s["reps"] or 0, s["weight"] or 0) for s in sets]
            else:
                # 没有逐组记录时，用计划值兜底，保证老数据也能出曲线
                reps_list = [(r["reps"], r["weight"])] * int(r["sets"])
            volume = sum(rep * wt for rep, wt in reps_list)
            max_weight = max((wt for _, wt in reps_list), default=0.0)
            est_1rm = max((wt * (1 + rep / 30.0) for rep, wt in reps_list if wt > 0), default=0.0)

            point = buckets.setdefault(r["plan_date"], {
                "date": r["plan_date"], "max_weight": 0.0, "volume": 0.0, "sets": 0, "est_1rm": 0.0,
            })
            point["max_weight"] = max(point["max_weight"], float(max_weight))
            point["volume"] = round(point["volume"] + volume, 2)
            point["sets"] += len(reps_list)
            point["est_1rm"] = round(max(point["est_1rm"], float(est_1rm)), 1)

        points = [buckets[k] for k in sorted(buckets)]
        pr_weight = max((p["max_weight"] for p in points), default=0.0)
        pr_date = next((p["date"] for p in points if p["max_weight"] == pr_weight), None)
        return {
            "name": name,
            "points": points,
            "pr_weight": pr_weight,
            "pr_date": pr_date,
            "best_volume": max((p["volume"] for p in points), default=0.0),
            "total_sets": sum(p["sets"] for p in points),
        }

    def copy_from(self, plan_id: int, plan_date: str) -> Optional[int]:
        """把某个历史计划（含部位、标题、备注、动作与休息时长）复制成一条新计划。

        返回新计划 id；源计划不存在或不属当前用户时返回 None。
        """
        source = self.get(plan_id)
        if source is None:
            return None
        try:
            cur = self.conn.execute(
                "INSERT INTO training_plans (user_id, plan_date, body_parts, title, note, status) "
                "VALUES (?, ?, ?, ?, ?, 'planned')",
                (self.user_id, plan_date, ",".join(source["body_parts"]), source["title"], source["note"]),
            )
            new_id = int(cur.lastrowid)
            for idx, e in enumerate(source["exercises"]):
                self.conn.execute(
                    "INSERT INTO plan_exercises (plan_id, name, sets, reps, weight, rest_seconds, note, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, '', ?)",
                    (new_id, e["name"], e["sets"], e["reps"], e["weight"], e["rest_seconds"], idx),
                )
            self.conn.commit()
            return new_id
        except Exception:
            self.conn.rollback()
            raise

    def add_exercise(self, plan_id: int, exercise: dict) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM plan_exercises WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        cur = self.conn.execute(
            "INSERT INTO plan_exercises (plan_id, name, sets, reps, weight, rest_seconds, note, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, '', ?)",
            (plan_id, exercise["name"], exercise["sets"], exercise["reps"],
             exercise["weight"], exercise.get("rest_seconds", 90), int(row["m"]) + 1),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_exercise(self, plan_id: int, exercise_id: int, fields: dict) -> bool:
        """局部更新计划内动作（如调整每组休息时长）。"""
        allowed = {"name", "sets", "reps", "weight", "rest_seconds"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False
        assignments = ", ".join(f"{k} = ?" for k in updates)
        cur = self.conn.execute(
            f"UPDATE plan_exercises SET {assignments} WHERE id = ? AND plan_id = ?",
            [*updates.values(), exercise_id, plan_id],
        )
        self.conn.commit()
        return cur.rowcount > 0

    def complete(self, plan_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE training_plans SET status = 'done', completed_at = datetime('now', 'localtime') "
            "WHERE id = ? AND user_id = ? AND status = 'planned'",
            (plan_id, self.user_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def reopen(self, plan_id: int) -> bool:
        """撤销打卡，退回今日计划。"""
        cur = self.conn.execute(
            "UPDATE training_plans SET status = 'planned', completed_at = NULL "
            "WHERE id = ? AND user_id = ? AND status = 'done'",
            (plan_id, self.user_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ---------------- 删除 ----------------
    def delete(self, plan_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM training_plans WHERE id = ? AND user_id = ?", (plan_id, self.user_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_exercise(self, plan_id: int, exercise_id: int) -> bool:
        if not self.exists(plan_id):
            return False
        cur = self.conn.execute(
            "DELETE FROM plan_exercises WHERE id = ? AND plan_id = ?", (exercise_id, plan_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    # ---------------- 统计 ----------------
    def count_done_since(self, since: date) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM training_plans "
            "WHERE user_id = ? AND status = 'done' AND plan_date >= ?",
            (self.user_id, since.isoformat()),
        ).fetchone()
        return int(row["n"])

    def totals(self) -> tuple[int, int, int, float]:
        """返回 (计划总数, 完成次数, 累计组数, 累计容量[仅统计已完成])。"""
        total = self.conn.execute(
            "SELECT COUNT(*) AS n FROM training_plans WHERE user_id = ?", (self.user_id,)
        ).fetchone()
        done = self.conn.execute(
            "SELECT COUNT(*) AS n FROM training_plans WHERE user_id = ? AND status = 'done'",
            (self.user_id,),
        ).fetchone()
        ex = self.conn.execute(
            "SELECT COALESCE(SUM(e.sets), 0) AS sets, COALESCE(SUM(e.sets * e.reps * e.weight), 0) AS vol "
            "FROM plan_exercises e JOIN training_plans p ON e.plan_id = p.id "
            "WHERE p.user_id = ? AND p.status = 'done'",
            (self.user_id,),
        ).fetchone()
        return int(total["n"]), int(done["n"]), int(ex["sets"]), round(float(ex["vol"]), 2)

    def body_part_distribution(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT body_parts FROM training_plans WHERE user_id = ? AND status = 'done'",
            (self.user_id,),
        ).fetchall()
        dist: dict[str, int] = {}
        for r in rows:
            for part in _split_parts(r["body_parts"]):
                dist[part] = dist.get(part, 0) + 1
        return dict(sorted(dist.items(), key=lambda kv: kv[1], reverse=True))


class BodyRepository:
    """体重记录仓储（接口保留，按用户隔离）。"""

    def __init__(self, conn: sqlite3.Connection, user_id: int) -> None:
        self.conn = conn
        self.user_id = user_id

    def list(self, limit: int = 200) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, date, weight, body_fat, note, created_at FROM body_records "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (self.user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def create(self, data: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO body_records (user_id, date, weight, body_fat, note) "
            "VALUES (:user_id, :date, :weight, :body_fat, :note)",
            {"user_id": self.user_id, **data},
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def delete(self, record_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM body_records WHERE id = ? AND user_id = ?", (record_id, self.user_id)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def latest(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT weight FROM body_records WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT 1",
            (self.user_id,),
        ).fetchone()
        return dict(row) if row else None


class StatsRepository:
    """概览统计（按用户）。"""

    def __init__(self, conn: sqlite3.Connection, today: date, user_id: int) -> None:
        self.conn = conn
        self.today = today
        self.plans = PlanRepository(conn, user_id)
        self.body = BodyRepository(conn, user_id)

    def summary(self) -> dict:
        total_plans, done_plans, total_sets, total_volume = self.plans.totals()
        latest = self.body.latest()
        return {
            "total_plans": total_plans,
            "done_plans": done_plans,
            "week_sessions": self.plans.count_done_since(_week_start(self.today)),
            "total_sets": total_sets,
            "total_volume": total_volume,
            "latest_weight": latest["weight"] if latest else None,
            "body_part_dist": self.plans.body_part_distribution(),
        }
