from __future__ import annotations

from datetime import date
from pathlib import Path

from pm_agent.memory.store import Store

_DEFAULT_DB = Path("state/pm-agent.db")


def dedupe_key(item_id: str, reminder_type: str, date_str: str | None = None) -> str:
    """生成幂等 key：{date}:{item_id}:{reminder_type}（PRD §11.1 简化版）。"""
    d = date_str or date.today().isoformat()
    return f"{d}:{item_id}:{reminder_type}"


def check_rate_limit(
    welink_id: str,
    today: str | None = None,
    max_per_day: int = 5,
    db_path: str | Path = _DEFAULT_DB,
) -> dict:
    """
    检查单责任人当天发送上限。

    返回 {"allowed": bool, "current": int, "limit": int}
    """
    store = Store(db_path)
    try:
        d = today or date.today().isoformat()
        current = store.count_by_owner_today(welink_id, d)
        return {
            "allowed": current < max_per_day,
            "current": current,
            "limit": max_per_day,
        }
    finally:
        store.close()


def check_run_limit(
    run_id: str,
    max_per_run: int = 50,
    db_path: str | Path = _DEFAULT_DB,
) -> dict:
    """
    检查单次运行发送上限。

    返回 {"allowed": bool, "current": int, "limit": int}
    """
    store = Store(db_path)
    try:
        current = store.count_run(run_id)
        return {
            "allowed": current < max_per_run,
            "current": current,
            "limit": max_per_run,
        }
    finally:
        store.close()
