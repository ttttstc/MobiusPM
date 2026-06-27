"""load_initial_context — 跨周期记忆加载（M3）"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from pm_agent.memory.store import DEFAULT_DB_PATH, Store

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_TEMPLATE_PATH = _PROMPT_DIR / "initial_user.md.j2"


def load_initial_context(
    trigger_reason: str = "wake",
    db_path: str | Path = DEFAULT_DB_PATH,
    lookback_days: int = 14,
    recent_decision_limit: int = 20,
    recent_send_limit: int = 20,
    max_total_chars: int = 8000,  # ~8k chars ≈ 2k tokens for mixed CN/EN
) -> str:
    """
    从 SQLite 加载跨周期上下文，渲染为 initial user message。

    加载内容（按优先级）：
    1. prior_brief — 最新 1 条 context_brief
    2. vanished_items — 失联事项
    3. recent_decisions — 最近 N 条 decision_log
    4. recent_sends — 最近 N 条 follow_up_log

    超出 max_total_chars 时按顺序裁剪：sends → decisions → brief 永远保留。
    """
    store = Store(db_path)
    try:
        # 1. prior brief
        prior_brief = None
        latest = store.get_latest_brief()
        if latest:
            prior_brief = latest["brief"]

        # 2. vanished items
        vanished_items = store.list_vanished()

        # 3. recent decisions
        cur = store._conn.execute(
            "SELECT decision_type, rationale, target_item_id, action_taken, created_at "
            "FROM decision_log ORDER BY created_at DESC LIMIT ?",
            (recent_decision_limit,),
        )
        recent_decisions = [
            {
                "decision_type": r[0],
                "rationale": r[1],
                "target_item_id": r[2],
                "action_taken": r[3],
                "created_at": r[4],
            }
            for r in cur.fetchall()
        ]

        # 4. recent sends
        cur2 = store._conn.execute(
            "SELECT item_id, owner, welink_id, reminder_type, send_status, created_at "
            "FROM follow_up_log ORDER BY created_at DESC LIMIT ?",
            (recent_send_limit,),
        )
        recent_sends = [
            {
                "item_id": r[0],
                "owner": r[1],
                "welink_id": r[2],
                "reminder_type": r[3],
                "send_status": r[4],
                "created_at": r[5],
            }
            for r in cur2.fetchall()
        ]

        # 5. pending candidates (from cron mode)
        pending_candidates = _load_pending()

        # 渲染模板
        template = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
        rendered = template.render(
            trigger_reason=trigger_reason,
            prior_brief=prior_brief,
            vanished_items=vanished_items,
            recent_decisions=recent_decisions,
            recent_sends=recent_sends,
            pending_candidates=pending_candidates,
        )

        # Token 预算裁剪
        if len(rendered) > max_total_chars:
            # 先裁 sends，再裁 decisions
            rendered = template.render(
                trigger_reason=trigger_reason,
                prior_brief=prior_brief,
                vanished_items=vanished_items,
                recent_decisions=recent_decisions[:5],
                recent_sends=[],
                pending_candidates=pending_candidates,
            )
            if len(rendered) > max_total_chars:
                # 再裁 decisions
                rendered = template.render(
                    trigger_reason=trigger_reason,
                    prior_brief=prior_brief,
                    vanished_items=vanished_items,
                    recent_decisions=[],
                    recent_sends=[],
                    pending_candidates=pending_candidates,
                )

        return rendered
    finally:
        store.close()


def _load_pending() -> list[dict]:
    """加载 cron 模式留下的待确认候选。"""
    pending_dir = Path("state/pending_for_wake")
    if not pending_dir.exists():
        return []
    # 读最新日期的 pending 文件
    files = sorted(pending_dir.glob("*.json"), reverse=True)
    if not files:
        return []
    import json

    try:
        with open(files[0], encoding="utf-8") as f:
            data = json.load(f)
            return data.get("candidates", []) if isinstance(data, dict) else data
    except Exception:
        return []
