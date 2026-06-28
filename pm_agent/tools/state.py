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


def query_history(
    item_id: str,
    max_records: int = 10,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    """
    查询某个事项的完整历史（状态 + 催办 + 决策）时间序列。

    返回 {"item_id": str, "state": ..., "follow_ups": [...], "decisions": [...]}
    """
    store = Store(db_path)
    try:
        state = store.get_item_state(item_id)
        cur = store._conn.execute(
            "SELECT reminder_type, send_status, message, dedupe_key, created_at "
            "FROM follow_up_log WHERE item_id=? ORDER BY created_at DESC LIMIT ?",
            (item_id, max_records),
        )
        follow_ups = [
            {"reminder_type": r[0], "send_status": r[1], "message": r[2],
             "dedupe_key": r[3], "created_at": r[4]}
            for r in cur.fetchall()
        ]
        cur2 = store._conn.execute(
            "SELECT decision_type, rationale, action_taken, created_at "
            "FROM decision_log WHERE target_item_id=? ORDER BY created_at DESC LIMIT ?",
            (item_id, max_records),
        )
        decisions = [
            {"decision_type": r[0], "rationale": r[1], "action_taken": r[2], "created_at": r[3]}
            for r in cur2.fetchall()
        ]
        return {
            "item_id": item_id,
            "state": state,
            "follow_ups": follow_ups,
            "decisions": decisions,
        }
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

        # 归档旧 brief（保留最近 max_briefs 条）
        _archive_old_briefs(store, max_briefs=30)

        return {"brief_id": brief_id, "status": "ok"}
    finally:
        store.close()


def _archive_old_briefs(store: Store, max_briefs: int = 30) -> None:
    """保留最近 max_briefs 条 brief，超出的归档到 state/archive/briefs/"""
    cur = store._conn.execute("SELECT COUNT(*) FROM context_brief")
    total = cur.fetchone()[0]
    if total <= max_briefs:
        return

    # 获取超出部分
    excess = total - max_briefs
    cur2 = store._conn.execute(
        "SELECT id, run_id, brief, token_count, created_at "
        "FROM context_brief ORDER BY id ASC LIMIT ?",
        (excess,),
    )
    old_rows = cur2.fetchall()

    archive_dir = Path("state/archive/briefs")
    archive_dir.mkdir(parents=True, exist_ok=True)

    for row in old_rows:
        # 按日期分文件
        date_str = row[4][:10] if row[4] else "unknown"
        archive_path = archive_dir / f"{date_str}.md"
        entry = (
            f"## Brief #{row[0]} · {row[1]}\n"
            f"**时间**: {row[4]}\n"
            f"**Token**: {row[3]}\n\n"
            f"{row[2]}\n\n---\n\n"
        )
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(entry)

    # 删除旧记录
    if old_rows:
        old_ids = [r[0] for r in old_rows]
        placeholders = ",".join("?" * len(old_ids))
        store._conn.execute(
            f"DELETE FROM context_brief WHERE id IN ({placeholders})",
            old_ids,
        )
        store._conn.commit()
