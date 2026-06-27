from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from pm_agent.memory.store import Store

_DEFAULT_DB = Path("state/pm-agent.db")


def query_state(
    item_id: Optional[str] = None,
    db_path: str | Path = _DEFAULT_DB,
) -> dict:
    """
    查询事项当前状态。

    item_id 为 None 时返回全部 item_state 摘要。
    返回 JSON-serializable dict。
    """
    store = Store(db_path)
    try:
        if item_id is not None:
            state = store.get_item_state(item_id)
            return {"found": state is not None, "state": state}
        else:
            # 返回全部
            cur = store._conn.execute(
                "SELECT item_id, last_seen_at, reminder_count, "
                "last_reminder_at, last_reminder_type, vanished_at "
                "FROM item_state"
            )
            rows = cur.fetchall()
            states = [
                {
                    "item_id": r[0],
                    "last_seen_at": r[1],
                    "reminder_count": r[2],
                    "last_reminder_at": r[3],
                    "last_reminder_type": r[4],
                    "vanished_at": r[5],
                }
                for r in rows
            ]
            return {"count": len(states), "states": states}
    finally:
        store.close()
