"""ask_human tool — MVP stdin 交互人机确认"""
from __future__ import annotations

import json
import sys
import uuid

from pm_agent.tools.notifier import store_confirmation_token


def ask_human(
    candidates: list[dict],
    question: str | None = None,
    run_id: str = "default",
    auto_yes: bool = False,
) -> dict:
    """
    人机确认接口。

    MVP: 打印候选清单到终端，PM 输入要催的事项 ID 确认。
    auto_yes=True 时跳过交互（用于测试/CI）。

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

    print("\n" + "=" * 60)
    print("跟催候选清单")
    print("=" * 60)
    if question:
        print(f"\n{question}\n")

    for i, c in enumerate(candidates, 1):
        print(f"  {i}. [{c.get('reminder_type', '?')}] {c.get('item_id', '?')}")
        print(f"     规则: {c.get('rule_id', '?')} | 严重度: {c.get('severity', '?')}")
        title = c.get("title", "")
        if len(title) > 60:
            title = title[:57] + "..."
        print(f"     标题: {title}")
        print()

    print("-" * 60)
    raw = input("请输入要催的事项 ID（逗号分隔，直接回车=全部确认，q=取消）: ").strip()

    if raw.lower() == "q":
        return {"confirmation_token": "", "confirmed_item_ids": [], "edited_messages": None}

    if raw == "":
        # 全部确认
        confirmed = [c["item_id"] for c in candidates]
    else:
        confirmed = [s.strip() for s in raw.split(",") if s.strip()]

    token = str(uuid.uuid4())
    store_confirmation_token(run_id, token)

    return {
        "confirmation_token": token,
        "confirmed_item_ids": confirmed,
        "edited_messages": None,
    }
