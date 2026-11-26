"""数据库体检 / 修复工具。

用法：
    python scripts/doctor.py         # 只体检，不改动数据
    python scripts/doctor.py --fix   # 先备份，再补齐缺失的表与列

适用于：启动报 no such table / no such column、换了版本后接口 500 等情况。
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import APP_VERSION, settings  # noqa: E402
from app.database import (  # noqa: E402
    REQUIRED_TABLES,
    get_connection,
    init_db,
    missing_tables,
)

# 各表后续版本新增的列，缺了会导致 SQL 报 no such column
EXPECTED_COLUMNS = {
    "training_plans": ["user_id"],
    "body_records": ["user_id"],
    "plan_exercises": ["rest_seconds", "skipped"],
    "exercise_sets": ["rpe"],
}


def inspect(db_path: Path) -> tuple[set[str], list[str], dict[str, list[str]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        missing = [t for t in REQUIRED_TABLES if t not in tables]
        lacking: dict[str, list[str]] = {}
        for table, cols in EXPECTED_COLUMNS.items():
            if table not in tables:
                continue
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            lack = [c for c in cols if c not in have]
            if lack:
                lacking[table] = lack
        return tables, missing, lacking
    finally:
        conn.close()


def main() -> int:
    fix = "--fix" in sys.argv
    db_path = settings.resolved_db_path

    print(f"健身记录 v{APP_VERSION} · 数据库体检")
    print(f"  Python    : {sys.version.split()[0]}")
    print(f"  项目根目录 : {PROJECT_ROOT}")
    print(f"  库文件     : {db_path}")
    print(f"  文件存在   : {'是' if db_path.exists() else '否（首次启动会自动创建）'}")
    if db_path.exists():
        print(f"  文件大小   : {db_path.stat().st_size} bytes")

    if not db_path.exists():
        init_db()
        print("  已自动创建空库。")
        return 0

    tables, missing, lacking = inspect(db_path)
    print(f"  现有表     : {', '.join(sorted(tables)) or '（空）'}")
    print(f"  缺失表     : {', '.join(missing) or '无'}")
    print(f"  缺失列     : {lacking or '无'}")

    if not missing and not lacking:
        conn = get_connection()
        try:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            plans = conn.execute("SELECT COUNT(*) FROM training_plans").fetchone()[0]
            print(f"  账号数     : {users}")
            print(f"  计划数     : {plans}")
        finally:
            conn.close()
        print("\n体检通过，数据库结构完整。")
        return 0

    if not fix:
        print("\n发现问题。加 --fix 参数即可自动补齐（会先备份当前库）。")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_suffix(db_path.suffix + f".bak-{stamp}")
    shutil.copy2(db_path, backup)
    print(f"\n已备份到：{backup}")

    # 若同名对象是视图/索引/触发器（会挡住建表），先清掉这个“假表”
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conflicts = [
            (r["type"], r["name"])
            for r in conn.execute(
                "SELECT type, name FROM sqlite_master WHERE type != 'table' AND name IN ({})".format(
                    ",".join("?" * len(REQUIRED_TABLES))
                ),
                REQUIRED_TABLES,
            ).fetchall()
        ]
        for obj_type, name in conflicts:
            drop = {"view": "DROP VIEW", "index": "DROP INDEX", "trigger": "DROP TRIGGER"}[obj_type]
            conn.execute(f"{drop} IF EXISTS {name}")
            print(f"  已清理同名冲突对象：{obj_type} {name}")
        conn.commit()
    finally:
        conn.close()

    try:
        init_db()
    except sqlite3.Error as exc:
        print(f"修复失败：{exc}")
        print("请检查库文件是否可写（被杀毒软件/OneDrive 占用时常见），或先把库文件复制出来再修。")
        return 2

    tables, missing, lacking = inspect(db_path)
    if missing or lacking:
        print(f"修复未完成，仍缺表：{missing}，缺列：{lacking}")
        return 3
    print("修复完成，数据库结构已补齐。可以重新启动服务了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
