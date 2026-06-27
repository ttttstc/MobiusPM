"""query_rule_suggestions — 规则建议器（LLM 可参考，非硬性指令）"""
from __future__ import annotations

from datetime import date

# ── 规则定义 ──


def _build_suggestions(work_items: list[dict]) -> list[dict]:
    """
    执行全部 DQ 规则 + R 规则，返回建议列表。

    每条建议: {item_id, rule_id, reminder_type, severity, rationale_hint}
    """
    suggestions: list[dict] = []
    today = date.today().isoformat()

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
        if not owner_list:
            suggestions.append({
                "item_id": item_id,
                "rule_id": "DQ-001",
                "reminder_type": "data_quality",
                "severity": "high",
                "rationale_hint": "活跃事项缺少责任人",
            })
            continue  # 缺责任人后续规则无法评估，跳过

        # DQ-003: P0/P1 缺计划时间
        if not due:
            suggestions.append({
                "item_id": item_id,
                "rule_id": "R-006",
                "reminder_type": "due_date_missing",
                "severity": "medium",
                "rationale_hint": "P0/P1 活跃事项缺少计划时间",
            })

        # ── R 规则 ──
        if status == "待验收":
            suggestions.append({
                "item_id": item_id,
                "rule_id": "R-001",
                "reminder_type": "acceptance_confirm",
                "severity": "high",
                "rationale_hint": "待验收事项需要确认验收进展",
            })

        elif status == "待验收待关闭":
            suggestions.append({
                "item_id": item_id,
                "rule_id": "R-001",
                "reminder_type": "close_confirm",
                "severity": "medium",
                "rationale_hint": "Close 但仍待验收，需确认是否可关闭",
            })

        elif status == "完成待关闭":
            suggestions.append({
                "item_id": item_id,
                "rule_id": "R-002",
                "reminder_type": "close_confirm",
                "severity": "medium",
                "rationale_hint": "已完成但 Open，需确认是否可关闭",
            })

        elif status == "开发中":
            if due and due < today:
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "R-003",
                    "reminder_type": "progress_check",
                    "severity": "high",
                    "rationale_hint": f"开发中超期，计划时间 {due} 早于今天",
                })
            elif due and _days_between(today, due) <= 2:
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "R-004",
                    "reminder_type": "progress_check",
                    "severity": "medium",
                    "rationale_hint": f"开发中临期，计划时间 {due} 距离今天 ≤2 天",
                })
            else:
                suggestions.append({
                    "item_id": item_id,
                    "rule_id": "R-003",
                    "reminder_type": "progress_check",
                    "severity": "low",
                    "rationale_hint": "开发中，无明确计划时间或未超期",
                })

        elif status == "待排期":
            suggestions.append({
                "item_id": item_id,
                "rule_id": "R-005",
                "reminder_type": "schedule_confirm",
                "severity": "high",
                "rationale_hint": "待排期事项需要确认排期",
            })

    return suggestions


def _days_between(d1: str, d2: str) -> int:
    """两个 ISO 日期字符串之间的天数差。"""
    try:
        from datetime import date as d

        return abs((d.fromisoformat(d1) - d.fromisoformat(d2)).days)
    except Exception:
        return 999  # 无法解析时视为不临期


# ── 公共接口 ──


def query_rule_suggestions(
    work_items: list[dict],
) -> dict:
    """
    对 WorkItem 列表执行规则扫描，返回建议。

    这是"建议"，LLM 可采纳/补充/拒绝——不是硬性指令。

    返回:
        {"suggestions": [...], "count": int, "summary": {...}}
    """
    suggestions = _build_suggestions(work_items)
    # 统计摘要
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
