from __future__ import annotations

from pathlib import Path

from pm_agent.memory.store import DEFAULT_DB_PATH, Store


def query_state(
    item_id: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
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
            states = store.list_all_item_states()
            return {"count": len(states), "states": states}
    finally:
        store.close()
