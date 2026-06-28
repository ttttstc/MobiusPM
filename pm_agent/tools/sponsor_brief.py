"""sponsor_brief — Sponsor 一页 Brief（M6 Feature 3）

设计要点：
- 文件输出：state/sponsor_brief/{date}_{run_id}.md
- 必须 < 30 行（一页 brief 核心承诺）
- 数字部分用代码渲染，叙事部分才让 LLM 写（避免数字打架）
- Ask ≤3 条，每条含 事项/状态/动作/决策/截止 5 字段
- Ask 必须可决策（每条 Sponsor 一次拍板能解决）
- 不自动发送给 Sponsor（PM 决定是否转发）
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

_BRIEF_DIR = Path("state/sponsor_brief")

# 距 630 节点天数（630 = 2026-06-30）
_TARGET_DATE = date(2026, 6, 30)

# Ask 字段的 5 段标识
_ASK_FIELDS = ["事项", "状态", "动作", "决策", "截止"]

# Ask 严重度映射（用中文字符）
_SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}

# PM 决策树 → Ask 字段生成
# Ask 必须可决策（"今天 17:00 前决定是否切分支"而非"请关注"）
_RISK_TO_ASK = {
    "R-009": {  # 状态回退
        "决策": "是否同意砍范围 / 切分支 / 增援",
        "动作": "今天 17:00 前确认根因",
    },
    "R-007": {  # 催办无响应
        "决策": "是否升级到上级",
        "动作": "今天联系上级拉群对账",
    },
    "R-003": {  # 开发中超期
        "决策": "是否延期 / 加人 / 缩范围",
        "动作": "今天重新评估剩余工作量",
    },
    "R-005": {  # 待排期
        "决策": "是否同意排期到 6/30 之后",
        "动作": "今天 PM 强制排期会议",
    },
    "R-010": {  # 反复催办
        "决策": "是否调整 Owner 或策略",
        "动作": "今天评估当前 Owner 是否合适",
    },
    "R-001": {  # 待验收 / 待关闭
        "决策": "是否接受当前进度可关闭",
        "动作": "今天验收 / 走关闭流程",
    },
    "R-002": {  # 完成待关闭
        "决策": "是否同意关闭",
        "动作": "今天关闭事项",
    },
    "R-008": {  # 状态停滞
        "决策": "是否重新评估优先级",
        "动作": "今天确认事项是否仍需推进",
    },
    "DQ-001": {  # 缺责任人
        "决策": "指派哪个 Owner",
        "动作": "今天 PM 指派负责人",
    },
    "DQ-002": {  # 负载过重
        "决策": "是否再分配 / 延期",
        "动作": "今天评估负载是否需调整",
    },
    "DQ-003": {  # 缺截止日期
        "决策": "是否补录截止时间 / 降级",
        "动作": "今天补录或评估优先级",
    },
}


def _format_ask(item: dict, sugg: dict, idx: int) -> str:
    """把单个事项 + 建议渲染为带编号的 1 行 Ask（含 5 字段）。"""
    rule_id = sugg["rule_id"]
    ask_tmpl = _RISK_TO_ASK.get(rule_id, {
        "决策": "PM 决策",
        "动作": "今天联系责任人确认",
    })
    sev = sugg.get("severity", "")
    sev_label = _SEVERITY_LABEL.get(sev, sev)
    item_id_short = item.get("item_id", "")[:8]
    title = (item.get("title") or "(无标题)")[:30]
    due = item.get("due_date") or "尽快"
    # 截止字段：基于 due_date + Ask 紧迫度
    if isinstance(due, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", due):
        deadline = due
    else:
        deadline = "本周内"

    return (
        f"{idx}. **{item_id_short}** {title} "
        f"[{sev_label}风险] → "
        f"建议{ask_tmpl['动作']} → "
        f"上级需{ask_tmpl['决策']} → "
        f"截止 **{deadline}**"
    )


def _pick_top_asks(
    work_items: list[dict],
    suggestions: list[dict],
    limit: int = 3,
) -> list[dict]:
    """选 ≤3 个最关键的 Ask（按 PM 决策树优先级）。"""
    items_by_id = {it["item_id"]: it for it in work_items}
    # 真风险优先（R-* > DQ-*），同类型内按 severity
    rule_priority = {
        "R-009": 0, "R-007": 1, "R-003": 2, "R-010": 3, "R-005": 4,
        "R-001": 5, "DQ-001": 6, "R-002": 7, "R-004": 8,
        "R-008": 9, "DQ-003": 10, "DQ-002": 11,
    }
    sev_order = {"high": 0, "medium": 1, "low": 2}
    sorted_sugg = sorted(
        suggestions,
        key=lambda s: (
            sev_order.get(s["severity"], 9),
            rule_priority.get(s["rule_id"], 99),
            s["rule_id"],
        ),
    )

    # 去重（同一 item_id 只选风险等级最高的）
    seen: set[str] = set()
    picks: list[dict] = []
    for s in sorted_sugg:
        if s["item_id"] in seen:
            continue
        seen.add(s["item_id"])
        item = items_by_id.get(s["item_id"], {})
        picks.append({"item": item, "suggestion": s})
        if len(picks) >= limit:
            break

    return picks


def _build_core_judgment(work_items: list[dict], suggestions: list[dict]) -> str:
    """1-2 句话的核心判断（数据驱动，不依赖 LLM）。"""
    high = sum(1 for s in suggestions if s["severity"] == "high")
    medium = sum(1 for s in suggestions if s["severity"] == "medium")
    today = date.today().isoformat()
    p0_overdue = sum(
        1 for it in work_items
        if it.get("priority_level") == "P0"
        and it.get("due_date")
        and it["due_date"] < today
        and it.get("normalized_status") not in ("已关闭", "挂起", "重复", "拒绝")
    )
    has_regression = any(s["rule_id"] == "R-009" for s in suggestions)
    has_no_response = any(s["rule_id"] == "R-007" for s in suggestions)

    if p0_overdue >= 1:
        return (
            f"项目状态承压：{p0_overdue} 项 P0 已超期未闭环；"
            f"高风险 {high} 项、中风险 {medium} 项。"
            f"项目经理需对以下决策项拍板。"
        )
    if has_regression:
        return (
            "项目出现状态回退，曾闭环事项重新出现需根因分析。"
            f"高风险 {high} 项、中风险 {medium} 项。"
        )
    if has_no_response:
        return (
            "存在催办无响应事项，跨团队协作受阻。"
            f"高风险 {high} 项、中风险 {medium} 项。"
        )
    if high == 0 and medium <= 3:
        return (
            f"项目整体可控：高风险 0 项、中风险 {medium} 项。"
            "项目经理可关注但无需立即决策。"
        )
    return (
        f"项目中等风险：高风险 {high} 项、中风险 {medium} 项。"
        "建议关注以下决策项。"
    )


def _build_metrics_table(snapshot: dict | None, previous: dict | None) -> str:
    """数字变化 vs 上周。"""
    if not snapshot:
        return (
            "| 指标 | 本周 |\n"
            "|------|------|\n"
            "| 暂无历史数据 | — |"
        )
    if not previous:
        return (
            "| 指标 | 本周 |\n"
            "|------|------|\n"
            f"| 活跃 | {snapshot.get('active', 0)} |\n"
            f"| 高风险 | {snapshot.get('high_risk', 0)} |\n"
            f"| 超期 | {snapshot.get('overdue', 0)} |\n"
            f"| 闭环 | {snapshot.get('closed', 0)} |"
        )

    rows = []
    for k, label in [
        ("total", "总数"),
        ("active", "活跃"),
        ("closed", "闭环"),
        ("high_risk", "高风险"),
        ("overdue", "超期"),
    ]:
        cur = snapshot.get(k, 0)
        prev = previous.get(k, 0)
        delta = cur - prev
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        rows.append(f"| {label} | {prev} | {cur} | {delta_str} |")
    return (
        "| 指标 | 上周 | 本周 | Δ |\n"
        "|------|------|------|------|\n"
        + "\n".join(rows)
    )


def _build_next_week_risks(
    work_items: list[dict],
    suggestions: list[dict],
) -> list[str]:
    """下周风险预判（≤3 条）。"""
    items: list[str] = []
    today = date.today().isoformat()

    # 临期 P0
    near_due_p0 = [
        it for it in work_items
        if it.get("priority_level") == "P0"
        and it.get("due_date")
        and it["due_date"] >= today
        and it.get("normalized_status") not in ("已关闭", "挂起", "重复", "拒绝")
    ]
    if near_due_p0:
        titles = "、".join(it["title"][:20] for it in near_due_p0[:3])
        items.append(f"临期 P0 {len(near_due_p0)} 项需进度确认（{titles}）")

    # 待排期 P0
    unscheduled = [
        it for it in work_items
        if it.get("priority_level") == "P0"
        and it.get("normalized_status") == "待排期"
    ]
    if unscheduled:
        items.append(f"P0 待排期 {len(unscheduled)} 项需 PM 强制排期")

    # 反复催办
    repeated = sum(1 for s in suggestions if s["rule_id"] == "R-010")
    if repeated:
        items.append(f"{repeated} 项反复催办，建议调整 Owner 或策略")

    if not items:
        items.append("无明显下周风险，建议保持当前节奏")
    return items[:3]


def _count_lines(text: str) -> int:
    """统计行数（不含纯空行）。"""
    return sum(1 for line in text.splitlines() if line.strip())


def write_sponsor_brief(
    work_items: list[dict],
    suggestions: list[dict],
    run_id: str,
    trend_snapshot: dict | None = None,
    trend_previous: dict | None = None,
    owner_load: dict | None = None,
    output_dir: str | Path = _BRIEF_DIR,
) -> dict:
    """生成 Sponsor 一页 Brief 文件。

    输入:
        work_items: read_excel 返回的 WorkItem 列表
        suggestions: query_rule_suggestions 返回的建议列表
        run_id: 本次运行 ID
        trend_snapshot: 当前 trend snapshot（可选，提供则填数字变化表）
        trend_previous: 上次 trend snapshot（可选）
        owner_load: query_owner_load 返回（可选）
        output_dir: 输出目录（默认 state/sponsor_brief）

    输出:
        {"status": "ok", "path": str, "char_count": int, "line_count": int}
    """
    today_str = date.today().isoformat()
    days_to_target = (_TARGET_DATE - date.today()).days

    # 1) 核心判断（数据驱动）
    core_judgment = _build_core_judgment(work_items, suggestions)

    # 2) 决策项（≤3 条）
    asks = _pick_top_asks(work_items, suggestions, limit=3)
    ask_lines = [_format_ask(a["item"], a["suggestion"], idx + 1) for idx, a in enumerate(asks)]
    ask_block = (
        "## 关键决策项\n\n" + "\n".join(ask_lines)
        if ask_lines else "## 关键决策项\n\n无"
    )

    # 3) 数字变化表
    metrics_table = _build_metrics_table(trend_snapshot, trend_previous)

    # 4) 下周风险
    next_risks = _build_next_week_risks(work_items, suggestions)
    next_risk_block = (
        "## 下周风险预判\n\n" + "\n".join(f"- {r}" for r in next_risks)
    )

    # 5) Owner 负载行（可选）
    owner_line = ""
    if owner_load and owner_load.get("summary", {}).get("overloaded_count", 0) > 0:
        s = owner_load["summary"]
        owner_line = (
            f"\n\n**人员负载**：{s['owner_count']} 人，"
            f"过载 {s['overloaded_count']} 人，"
            f"瓶颈 {s['bottleneck_count']} 人"
        )

    # 6) 拼装 Brief（强约束 < 30 行）
    brief = (
        f"# 上级简报 · 630 节点 · {today_str}\n"
        f"**距 630 节点**: {days_to_target} 天\n"
        f"\n"
        f"## 核心判断\n"
        f"\n"
        f"{core_judgment}\n"
        f"\n"
        f"{ask_block}\n"
        f"\n"
        f"## 数字变化 vs 上周\n"
        f"\n"
        f"{metrics_table}\n"
        f"{owner_line}\n"
        f"\n"
        f"{next_risk_block}\n"
    )

    # 7) 写盘
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_run = run_id.replace("/", "_").replace("..", "_")
    file_name = f"{today_str}_{safe_run}.md"
    out_path = output_dir / file_name
    out_path.write_text(brief, encoding="utf-8")

    return {
        "status": "ok",
        "path": str(out_path),
        "char_count": len(brief),
        "line_count": _count_lines(brief),
    }