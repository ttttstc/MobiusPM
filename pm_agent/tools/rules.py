"""query_rule_suggestions — 规则建议器（LLM 可参考，非硬性指令）"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from pm_agent.memory.store import DEFAULT_DB_PATH, Store


def _build_suggestions(work_items: list[dict], db_path: str | Path | None = None) -> list[dict]:
    """
    执行全部 DQ 规则 + R 规则，返回建议列表。

    每条建议: {item_id, rule_id, reminder_type, severity, rationale_hint}
    """
    suggestions: list[dict] = []
    today = date.today().isoformat()

    # ── 状态依赖规则：需要查 DB ──
    store = None
    if db_path:
        store = Store(db_path)

    # ── DQ-002: 责任人负载过重检测 ──
    owner_active: dict[str, int] = {}
    for it in work_items:
        if it["normalized_status"] in ("已关闭", "挂起", "重复", "拒绝"):
            continue
        for owner in it.get("owner_list", []):
            owner_active[owner] = owner_active.get(owner, 0) + 1

    try:
        for it in work_items:
            item_id = it["item_id"]
            status = it["normalized_status"]
            priority = it["priority_level"]
            due = it.get("due_date")
            owner_list = it.get("owner_list", [])
            title = it.get("title", "")
            source = it.get("source", "")

            # 跳过不跟催的状态
            if status in ("已关闭", "挂起", "重复", "拒绝"):
                continue

            # 非 P0/P1 默认不自动催
            if priority not in ("P0", "P1"):
                continue

            # ── DQ 规则 ──

            # DQ-001: 活跃事项缺责任人
            if not owner_list:
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "DQ-001",
                    "reminder_type": "data_quality",
                    "severity": "high",
                    "rationale_hint": "活跃事项缺少责任人，无法确定跟催对象",
                })
                continue  # 缺责任人后续规则无法评估

            # DQ-002: 责任人负载过重（>8条活跃 + P0/P1）
            for owner in owner_list:
                if owner_active.get(owner, 0) > 8:
                    suggestions.append({
                        "item_id": item_id,
                        "rule_id": "DQ-002",
                        "reminder_type": "data_quality",
                        "severity": "medium",
                        "rationale_hint": f"责任人 {owner} 活跃事项过多（{owner_active[owner]}条），建议关注负载",
                    })
                    break  # 每个事项只报一次

            # DQ-003: P0/P1 缺计划时间（原 R-006 改名）
            if not due:
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "DQ-003",
                    "reminder_type": "due_date_missing",
                    "severity": "medium",
                    "rationale_hint": "P0/P1 活跃事项缺少计划完成时间",
                })

            # ── R 规则 ──

            # R-001: 待验收
            # 注意：待验收是事项的正常流转状态，本身不是高风险，仅作为提示项
            if status == "待验收":
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "R-001",
                    "reminder_type": "acceptance_confirm",
                    "severity": "low",
                    "rationale_hint": "待验收事项需确认验收进展（提示项，非高风险）",
                })

            # R-001b: 待验收待关闭
            elif status == "待验收待关闭":
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "R-001",
                    "reminder_type": "close_confirm",
                    "severity": "medium",
                    "rationale_hint": "Close 但仍待验收，需确认是否可关闭",
                })

            # R-002: 完成待关闭
            elif status == "完成待关闭":
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "R-002",
                    "reminder_type": "close_confirm",
                    "severity": "medium",
                    "rationale_hint": "已完成但 Open，需确认是否可关闭",
                })

            # R-003: 开发中（无日期或未超期）
            # R-004: 开发中临期
            elif status == "开发中":
                if due and due < today:
                    suggestions.append({
                        "item_id": item_id,
                        "rule_id": "R-003",
                        "reminder_type": "progress_check",
                        "severity": "high",
                        "rationale_hint": f"开发中超期，计划时间 {due} 早于今天",
                    })
                elif due and _days_between(today, due) <= 3:
                    suggestions.append({
                        "item_id": item_id,
                        "rule_id": "R-004",
                        "reminder_type": "progress_check",
                        "severity": "medium",
                        "rationale_hint": f"开发中临期，计划时间 {due} 距离今天 ≤3 天",
                    })
                else:
                    suggestions.append({
                        "item_id": item_id,
                        "rule_id": "R-003",
                        "reminder_type": "progress_check",
                        "severity": "low",
                        "rationale_hint": "开发中，无明确计划时间或未超期",
                    })

            # R-005: 待排期
            elif status == "待排期":
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "R-005",
                    "reminder_type": "schedule_confirm",
                    "severity": "high",
                    "rationale_hint": "待排期事项需要确认排期计划",
                })

            # ── 历史依赖规则（需要 db_path）──
            if store is not None:
                # R-007: 上次催办后 >3 工作日无响应
                cur = store._conn.execute(
                    "SELECT send_status, created_at FROM follow_up_log "
                    "WHERE item_id=? AND send_status IN ('success','mock') "
                    "ORDER BY created_at DESC LIMIT 1",
                    (item_id,),
                )
                last_follow = cur.fetchone()
                if last_follow:
                    days_since = _days_between(today, last_follow[1][:10])
                    if days_since > 3:
                        suggestions.append({
                            "item_id": item_id,
                            "rule_id": "R-007",
                            "reminder_type": "escalation",
                            "severity": "high",
                            "rationale_hint": f"上次催办 {days_since} 天前无响应，建议升级处理",
                        })

                # R-008: 状态长期停滞（>30 天无变化）
                state = store.get_item_state(item_id)
                if state and state.get("last_seen_at"):
                    days_stale = _days_between(today, state["last_seen_at"][:10])
                    if days_stale > 30:
                        suggestions.append({
                            "item_id": item_id,
                            "rule_id": "R-008",
                            "reminder_type": "stagnation_alert",
                            "severity": "medium",
                            "rationale_hint": f"事项状态停滞 {days_stale} 天无变化",
                        })

                # R-009: 状态回退检测（曾标记 vanished 后又出现）
                if state and state.get("is_vanished"):
                    suggestions.append({
                        "item_id": item_id,
                        "rule_id": "R-009",
                        "reminder_type": "regression_alert",
                        "severity": "high",
                        "rationale_hint": "该事项曾被标记为失联，重新出现需确认原因",
                    })

                # R-010: 连续催办标记（≥2 次同类型催办视为反复无效）
                cur2 = store._conn.execute(
                    "SELECT COUNT(*) FROM follow_up_log "
                    "WHERE item_id=? AND send_status IN ('success','mock')",
                    (item_id,),
                )
                total_sent = cur2.fetchone()[0]
                if total_sent >= 2:
                    suggestions.append({
                        "item_id": item_id,
                        "rule_id": "R-010",
                        "reminder_type": "escalation",
                        "severity": "medium",
                        "rationale_hint": f"该事项已催办 {total_sent} 次，建议评估是否升级或调整策略",
                    })

    finally:
        if store:
            store.close()

    return suggestions


def _days_between(d1: str, d2: str) -> int:
    """两个 ISO 日期字符串之间的天数差。"""
    try:
        from datetime import date as d

        return abs((d.fromisoformat(d1) - d.fromisoformat(d2)).days)
    except Exception:
        return 999


# ── 公共接口 ──


def query_rule_suggestions(
    work_items: list[dict],
    db_path: str | Path | None = None,
) -> dict:
    """
    对 WorkItem 列表执行规则扫描，返回建议。

    这是"建议"，LLM 可采纳/补充/拒绝——不是硬性指令。

    若提供 db_path，还会执行历史依赖规则（R-007 ~ R-010）。

    返回:
        {"suggestions": [...], "count": int, "summary": {"by_rule": ..., "by_severity": ...}}
    """
    suggestions = _build_suggestions(work_items, db_path)
    by_rule: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for s in suggestions:
        by_rule[s["rule_id"]] = by_rule.get(s["rule_id"], 0) + 1
        by_severity[s["severity"]] = by_severity.get(s["severity"], 0) + 1

    return {
        "suggestions": suggestions,
        "count": len(suggestions),
        "summary": {
            "by_rule": by_rule,
            "by_severity": by_severity,
        },
    }
