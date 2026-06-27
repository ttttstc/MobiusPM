from __future__ import annotations

import uuid
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


def write_decision(
    decision_type: str,
    rationale: str,
    run_id: str,
    target_item_id: str | None = None,
    action_taken: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    """
    写决策日志。

    rationale 非空且 ≥ 20 字符强制（P4 原则），否则抛 ValueError。

    返回 {"decision_id": str, "status": "ok"}
    """
    rationale = (rationale or "").strip()
    if len(rationale) < 20:
        raise ValueError(
            f"rationale 至少 20 字符，当前 {len(rationale)} 字符。"
            "决策必须留理由（P4 原则）。"
        )

    decision_id = str(uuid.uuid4())
    store = Store(db_path)
    try:
        store.insert_decision(
            decision_id=decision_id,
            run_id=run_id,
            decision_type=decision_type,
            rationale=rationale,
            target_item_id=target_item_id,
            action_taken=action_taken,
        )
        return {"decision_id": decision_id, "status": "ok"}
    finally:
        store.close()


def update_context_brief(
    brief: str,
    run_id: str,
    max_tokens: int = 1000,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    """
    写项目摘要（每次 loop 结束更新）。

    brief 长度 ≤ max_tokens 字符（粗略估算），超出报 ValueError。

    返回 {"brief_id": int, "status": "ok"}
    """
    brief = (brief or "").strip()
    if len(brief) > max_tokens:
        raise ValueError(
            f"brief 长度 {len(brief)} 超出上限 {max_tokens} 字符"
        )

    # 粗略 token 估算: 中文 ~1 char/token, 英文 ~4 char/token
    token_count = len(brief)

    store = Store(db_path)
    try:
        store.insert_brief(run_id=run_id, brief=brief, token_count=token_count)
        # 获取刚插入的 id
        latest = store.get_latest_brief()
        brief_id = latest["id"] if latest else -1
        return {"brief_id": brief_id, "status": "ok"}
    finally:
        store.close()
