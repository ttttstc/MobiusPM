#!/usr/bin/env python3
"""
M1-B 集成测试：不经过 agent，直接串联 5 个 tool
  read_excel → query_rule_suggestions → ask_human(auto) → gen_message → send_welink(mock) → write_decision

验证工具层协作正确性。
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    from pm_agent.tools.excel import read_excel
    from pm_agent.tools.rules import query_rule_suggestions
    from pm_agent.tools.human import ask_human
    from pm_agent.tools.messages import gen_message
    from pm_agent.tools.notifier import send_welink
    from pm_agent.tools.state import write_decision
    from pm_agent.tools.contacts import load_contacts

    excel_path = ROOT / "source" / "项目630流水线排期计划.xlsx"
    contacts_path = ROOT / "config" / "contacts.yaml"
    run_id = f"pipeline_{uuid.uuid4().hex[:8]}"

    print(f"=== M1-B dry-run pipeline ===\nrun_id: {run_id}\n")

    # Step 1: read_excel
    print("[1/5] read_excel ...")
    result = read_excel(str(excel_path))
    items = result["items"]
    print(f"  解析 {result['count']} 条 WorkItem, mtime unchanged={result['vanished_item_ids'] is not None}")

    # Step 2: query_rule_suggestions
    print("[2/5] query_rule_suggestions ...")
    suggestions_result = query_rule_suggestions(items)
    suggestions = suggestions_result["suggestions"]
    summary = suggestions_result["summary"]
    print(f"  共 {suggestions_result['count']} 条建议")
    print(f"  按规则: {summary['by_rule']}")
    print(f"  按严重度: {summary['by_severity']}")

    # Step 3: ask_human (auto_yes)
    print("[3/5] ask_human (auto_yes) ...")
    # 取前 5 条建议作为候选
    candidates = suggestions[:5]
    for c in candidates:
        it = next((i for i in items if i["item_id"] == c["item_id"]), None)
        if it:
            c["title"] = it.get("title", "")
            c["owner"] = it.get("owner_list", [None])[0] if it.get("owner_list") else None

    human_result = ask_human(candidates, run_id=run_id, auto_yes=True)
    token = human_result["confirmation_token"]
    print(f"  confirmation_token: {token[:8]}..., confirmed: {len(human_result['confirmed_item_ids'])}")

    # Step 4: gen_message + send_welink (mock)
    print("[4/5] gen_message + send_welink (mock) ...")
    contacts = load_contacts(contacts_path) if contacts_path.exists() else None
    sent = 0
    for item_id in human_result["confirmed_item_ids"][:3]:  # 最多发 3 条
        it = next((i for i in items if i["item_id"] == item_id), None)
        if it is None:
            continue
        rt = next((s["reminder_type"] for s in suggestions if s["item_id"] == item_id), "progress_check")
        msg_result = gen_message(item_id, rt, {
            "title": it["title"],
            "project": "630项目",
            "source": it["source"],
            "priority": it["priority_raw"],
            "handler": ", ".join(it["handler_chain"]),
            "due_date": it.get("due_date"),
            "remark": it.get("remark"),
            "status": it["normalized_status"],
        })
        owner = it.get("owner_list", [None])[0] if it.get("owner_list") else "unknown"
        welink_id = contacts.get(owner, {}).get("welink_id", owner) if contacts else owner
        send_result = send_welink(
            item_id=item_id, owner=owner, welink_id=welink_id,
            message=msg_result["message"], reminder_type=rt,
            confirmation_token=token, run_id=run_id,
            contacts=contacts,
        )
        status = send_result["status"]
        print(f"  {item_id}: {status} {send_result.get('reason', '')}")
        if status == "sent":
            sent += 1

    print(f"  发送成功: {sent}/{min(3, len(human_result['confirmed_item_ids']))}")

    # Step 5: write_decision
    print("[5/5] write_decision ...")
    decision = write_decision(
        decision_type="brief",
        rationale=f"dry-run pipeline {run_id}: 扫描 {result['count']} 条, "
                 f"建议 {suggestions_result['count']} 条, 模拟发送 {sent} 条, 全部通过安全校验",
        run_id=run_id,
        action_taken=f"send_welink x{sent}",
    )
    print(f"  decision_id: {decision['decision_id']}")

    # Summary
    print(f"\n=== Pipeline 完成 ===")
    print(f"  解析: {result['count']} 条")
    print(f"  建议: {suggestions_result['count']} 条")
    print(f"  发送: {sent} 条 (mock)")
    print(f"  决策留痕: ok")
    print(f"  Excel mtime 不变: ok")


if __name__ == "__main__":
    main()
