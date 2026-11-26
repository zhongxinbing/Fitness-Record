"""SQLite 数据库访问层。

数据模型：
  training_plans（训练计划，一条计划可覆盖多个部位）
      ├─ body_parts  逗号分隔，如 "胸,肩"
      ├─ status      planned（待完成）/ done（已打卡，进入历史）
      └─ plan_exercises（计划内的动作明细，一对多，级联删除）
  body_records（体重记录，接口保留）

首次启动会把旧版 training_sessions / session_exercises 数据平滑迁移为已完成的计划。
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Generator

from app.config import settings

logger = logging.getLogger("fitness")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    expires_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS training_plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL DEFAULT 0,
    plan_date    TEXT    NOT NULL,
    body_parts   TEXT    NOT NULL,
    title        TEXT    NOT NULL DEFAULT '',
    note         TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'planned',
    completed_at TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS plan_exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     INTEGER NOT NULL REFERENCES training_plans(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    sets        INTEGER NOT NULL DEFAULT 3,
    reps        INTEGER NOT NULL DEFAULT 10,
    weight      REAL    NOT NULL DEFAULT 0,
    rest_seconds INTEGER NOT NULL DEFAULT 90,
    skipped     INTEGER NOT NULL DEFAULT 0,
    note        TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS body_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL DEFAULT 0,
    date        TEXT    NOT NULL,
    weight      REAL    NOT NULL,
    body_fat    REAL,
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS exercise_sets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id INTEGER NOT NULL REFERENCES plan_exercises(id) ON DELETE CASCADE,
    set_index   INTEGER NOT NULL,
    done        INTEGER NOT NULL DEFAULT 0,
    reps        INTEGER,
    weight      REAL,
    rpe         REAL,
    done_at     TEXT,
    UNIQUE (exercise_id, set_index)
);

CREATE INDEX IF NOT EXISTS idx_plan_date   ON training_plans(plan_date);
CREATE INDEX IF NOT EXISTS idx_plan_status ON training_plans(status);
CREATE INDEX IF NOT EXISTS idx_plan_ex     ON plan_exercises(plan_id);
CREATE INDEX IF NOT EXISTS idx_set_ex      ON exercise_sets(exercise_id);
CREATE INDEX IF NOT EXISTS idx_sess_user   ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_body_date   ON body_records(date);
"""

# user_id 相关索引单独建：旧库要先 ALTER TABLE 补列，索引才能建，不能写进 SCHEMA
USER_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_plan_user ON training_plans(user_id);
CREATE INDEX IF NOT EXISTS idx_body_user ON body_records(user_id);
"""


REQUIRED_TABLES = (
    "users",
    "auth_sessions",
    "training_plans",
    "plan_exercises",
    "exercise_sets",
    "body_records",
)
# 已成功初始化过的库（每个进程一份，避免每个请求都去查 sqlite_master）
_READY_DBS: set[str] = set()


def table_names(conn: sqlite3.Connection) -> set[str]:
    """当前库里已有的表名。"""
    return {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }


def missing_tables(conn: sqlite3.Connection) -> list[str]:
    names = table_names(conn)
    return [t for t in REQUIRED_TABLES if t not in names]


def ensure_db_ready(conn: sqlite3.Connection) -> None:
    """请求级自愈：万一启动时初始化没落到这个库文件上，这里补一次建表。

    典型场景：旧库被 OneDrive/杀毒软件锁住、启动进程与请求进程看到的不是同一个
    文件，或者直接用了旧版本的 database.py。补齐失败时抛出可读的错误，避免前端
    只看到 “no such table: users”。
    """
    key = str(settings.resolved_db_path)
    missing = missing_tables(conn)          # 每条请求一次轻量校验（sqlite_master 查询）
    if not missing:
        return

    logger.warning("数据库缺少表 %s，尝试自动补齐：%s", missing, key)
    init_db()
    missing = missing_tables(conn)
    if missing:
        raise RuntimeError(
            f"数据库仍未初始化（缺表 {missing}）：{key}；"
            "请确认数据库文件可写，或运行 python scripts/doctor.py --fix"
        )


def get_connection() -> sqlite3.Connection:
    """获取数据库连接（行以 dict 访问）。

    注意：FastAPI 的同步依赖与同步路由可能运行在线程池的不同线程中，因此关闭
    sqlite3 的同线程检查；每个连接仍是请求独占，不存在并发复用。
    """
    conn = sqlite3.connect(settings.resolved_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _migrate_legacy(conn: sqlite3.Connection) -> None:
    """把旧版「训练分组」数据迁移为已完成计划，随后移除旧表。"""
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if "training_sessions" not in tables:
        return
    try:
        sessions = conn.execute(
            "SELECT id, date, body_part, title, note, created_at FROM training_sessions"
        ).fetchall()
        for s in sessions:
            cur = conn.execute(
                "INSERT INTO training_plans (plan_date, body_parts, title, note, status, completed_at, created_at) "
                "VALUES (?, ?, ?, ?, 'done', ?, ?)",
                (s["date"], s["body_part"], s["title"], s["note"], s["created_at"], s["created_at"]),
            )
            new_id = int(cur.lastrowid)
            if "session_exercises" in tables:
                conn.execute(
                    "INSERT INTO plan_exercises (plan_id, name, sets, reps, weight, note, sort_order) "
                    "SELECT ?, name, sets, reps, weight, note, sort_order FROM session_exercises "
                    "WHERE session_id = ?",
                    (new_id, s["id"]),
                )
        conn.execute("DROP TABLE IF EXISTS session_exercises")
        conn.execute("DROP TABLE IF EXISTS training_sessions")
        logger.info("旧版训练数据已迁移为 %d 条历史计划", len(sessions))
    except sqlite3.Error:
        logger.exception("旧数据迁移失败，跳过迁移")
        conn.rollback()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """轻量增量迁移：为已存在的旧表补齐后续版本新增的列。"""
    ex_columns = {r["name"] for r in conn.execute("PRAGMA table_info(plan_exercises)").fetchall()}
    if "rest_seconds" not in ex_columns:
        # 每组休息时长（秒），默认 90 秒
        conn.execute(
            "ALTER TABLE plan_exercises ADD COLUMN rest_seconds INTEGER NOT NULL DEFAULT 90"
        )
        logger.info("已为 plan_exercises 补充 rest_seconds 列")
    if "skipped" not in ex_columns:
        # 训练中「跳过该动作」，跳过的动作不计入计划必做组数
        conn.execute(
            "ALTER TABLE plan_exercises ADD COLUMN skipped INTEGER NOT NULL DEFAULT 0"
        )
        logger.info("已为 plan_exercises 补充 skipped 列")

    set_columns = {r["name"] for r in conn.execute("PRAGMA table_info(exercise_sets)").fetchall()}
    if set_columns and "rpe" not in set_columns:
        # 每组主观强度（RPE 1–10，0.5 步进）
        conn.execute("ALTER TABLE exercise_sets ADD COLUMN rpe REAL")
        logger.info("已为 exercise_sets 补充 rpe 列")

    # 多用户支持：历史单机数据先落为 user_id = 0，由首个注册用户认领
    for table in ("training_plans", "body_records"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "user_id" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
            logger.info("已为 %s 补充 user_id 列", table)


def init_db() -> None:
    """初始化表结构，并在需要时执行一次性迁移。

    顺序很关键：建表（IF NOT EXISTS）→ 补旧表缺失列 → 旧数据迁移 → 提交。
    user_id 索引必须在补列之后创建，否则旧库会因“列不存在”启动失败。
    """
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)
        conn.executescript(USER_INDEXES)
        _migrate_legacy(conn)
        conn.commit()
        _READY_DBS.add(str(settings.resolved_db_path))
        logger.info("数据库就绪: %s（表：%s）", settings.resolved_db_path,
                    ",".join(sorted(REQUIRED_TABLES)))
    except sqlite3.Error:
        logger.exception("数据库初始化失败，请检查 %s 是否可写", settings.resolved_db_path)
        raise
    finally:
        conn.close()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI 依赖：请求级连接，结束后自动关闭。"""
    conn = get_connection()
    try:
        ensure_db_ready(conn)
        yield conn
    finally:
        conn.close()
