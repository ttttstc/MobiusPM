"""ask_human tool — 终端交互人机确认（M2 增强展示）"""
from __future__ import annotations

import uuid

from pm_agent.tools.notifier import store_confirmation_token

_SEVERITY_MAP = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}
_TYPE_CN = {
    "acceptance_confirm": "验收确认",
    "progress_check": "进度检查",
    "schedule_confirm": "排期确认",
    "due_date_missing": "缺截止日期",
    "close_confirm": "闭环确认",
}


def _format_table(candidates: list[dict]) -> str:
    """渲染候选清单为对齐表格。"""
    header = f"{'#':<4} {'类型':<10} {'严重度':<10} {'事项ID':<14} {'标题'}"
    lines = [header, "-" * 80]
    for i, c in enumerate(candidates, 1):
        rt = _TYPE_CN.get(c.get("reminder_type", ""), c.get("reminder_type", "?"))
        sev = _SEVERITY_MAP.get(c.get("severity", ""), c.get("severity", "?"))
        title = c.get("title", "")
        if len(title) > 40:
            title = title[:37] + "..."
        lines.append(f"{i:<4} {rt:<10} {sev:<10} {c.get('item_id', '?'):<14} {title}")
    return "\n".join(lines)


def ask_human(
    candidates: list[dict],
    question: str | None = None,
    run_id: str = "default",
    auto_yes: bool = False,
) -> dict:
    """
    人机确认接口。

    展示跟催候选清单表格，PM 输入事项 ID 确认发送。

    返回:
        {confirmation_token, confirmed_item_ids, edited_messages?}
    """
    if auto_yes:
        token = str(uuid.uuid4())
        store_confirmation_token(run_id, token)
        return {
            "confirmation_token": token,
            "confirmed_item_ids": [c["item_id"] for c in candidates],
            "edited_messages": None,
        }

    print()
    print("=" * 60)
    print("  MobiusPM · 跟催候选清单")
    print("=" * 60)
    if question:
        print(f"\n  {question}\n")

    print(_format_table(candidates))
    print()

    # 按类型统计
    type_counts: dict[str, int] = {}
    for c in candidates:
        rt = c.get("reminder_type", "unknown")
        type_counts[rt] = type_counts.get(rt, 0) + 1
    summary = " | ".join(f"{_TYPE_CN.get(k, k)}: {v}" for k, v in type_counts.items())
    print(f"  统计: {len(candidates)} 条候选 ({summary})")

    print("-" * 60)
    raw = input("请输入要催的事项 ID（逗号分隔，回车=全部确认，q=取消）: ").strip()

    if raw.lower() == "q":
        return {"confirmation_token": "", "confirmed_item_ids": [], "edited_messages": None}

    if raw == "":
        confirmed = [c["item_id"] for c in candidates]
    else:
        confirmed = [s.strip() for s in raw.split(",") if s.strip()]

    token = str(uuid.uuid4())
    store_confirmation_token(run_id, token)

    print(f"  ✓ 已确认 {len(confirmed)} 条，token={token[:8]}...\n")

    return {
        "confirmation_token": token,
        "confirmed_item_ids": confirmed,
        "edited_messages": None,
    }
