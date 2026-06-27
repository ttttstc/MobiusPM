"""write_html_dashboard — 生成项目大盘 HTML 看板（DESIGN.md 视觉系统）

设计原则：
- 自包含单文件：CSS inline、JS inline、无外链字体/资源
- 深色单一主题：OKLCH 颜色空间，琥珀强调
- 三层信息折叠：健康度总览 → 风险明细 → 建议行动
- 表格语义优先，无卡片堆叠
- 状态双通道：颜色 + 形状（●▲■✕⏸）+ 文本
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Template

from pm_agent.memory.store import DEFAULT_DB_PATH, Store
from pm_agent.tools.rules import query_rule_suggestions

_DASHBOARD_DIR = Path("state/dashboards")

_CSS = """\
:root {
  --bg:        oklch(13% 0.012 250);
  --bg-elev:   oklch(17% 0.015 250);
  --bg-rule:   oklch(22% 0.018 250);
  --bg-hover:  oklch(20% 0.015 250);
  --ink-1:     oklch(96% 0.005 250);
  --ink-2:     oklch(78% 0.010 250);
  --ink-3:     oklch(55% 0.012 250);
  --ink-4:     oklch(38% 0.010 250);
  --accent:    oklch(78% 0.18  75);
  --accent-soft: oklch(45% 0.12 75);
  --state-ok:   oklch(70% 0.16 145);
  --state-warn: oklch(78% 0.18  75);
  --state-crit: oklch(64% 0.22  25);
  --state-mute: oklch(50% 0.008 250);
  --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", "Cascadia Mono", Consolas, "Liberation Mono", Menlo, monospace;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 16px; }
body {
  background: var(--bg);
  color: var(--ink-1);
  font-family: var(--font-sans);
  font-size: 0.875rem;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  font-kerning: normal;
}
main.dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--space-7) var(--space-5);
}
.mono { font-family: var(--font-mono); font-feature-settings: "tnum" 1, "ss01" 1; }
.tnum { font-variant-numeric: tabular-nums; }

/* ── Header ── */
.dash-header { margin-bottom: var(--space-7); }
.dash-header h1 {
  font-family: var(--font-mono);
  font-size: 2rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--ink-1);
  line-height: 1.1;
}
.dash-header .meta {
  margin-top: var(--space-3);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--ink-3);
}
.dash-header .meta span + span::before { content: " · "; margin: 0 var(--space-1); color: var(--ink-4); }

/* ── Section header (水平线 + 标题) ── */
.section { margin-top: var(--space-7); }
.section-title {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--ink-1);
  margin-bottom: var(--space-5);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--bg-rule);
}

/* ── Stats row ── */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border-top: 1px solid var(--bg-rule);
  border-bottom: 1px solid var(--bg-rule);
}
.stat { padding: var(--space-4) var(--space-5); border-right: 1px solid var(--bg-rule); }
.stat:last-child { border-right: none; }
.stat-label {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: var(--space-2);
}
.stat-value {
  font-family: var(--font-mono);
  font-size: 2rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--ink-1);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.stat-value.crit { color: var(--state-crit); }
.stat-value.warn { color: var(--state-warn); }
.stat-value.ok { color: var(--state-ok); }
.stat-meta { margin-top: var(--space-2); font-size: 0.75rem; color: var(--ink-3); }

/* ── Status pill ── */
.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  white-space: nowrap;
}
.pill-glyph {
  font-family: var(--font-mono);
  font-size: 0.875rem;
  line-height: 1;
}
.pill-crit .pill-glyph, .pill-crit { color: var(--state-crit); }
.pill-warn .pill-glyph, .pill-warn { color: var(--state-warn); }
.pill-ok   .pill-glyph, .pill-ok   { color: var(--state-ok); }
.pill-mute .pill-glyph, .pill-mute { color: var(--ink-3); }

/* ── Risk table ── */
table.risks {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}
table.risks thead th {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink-3);
  text-align: left;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--bg-rule);
}
table.risks tbody td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--bg-rule);
  vertical-align: top;
}
table.risks tbody tr:hover { background: var(--bg-hover); }
table.risks tbody tr:last-child td { border-bottom: 1px solid var(--bg-rule); }
.col-status { width: 110px; }
.col-id     { width: 110px; font-family: var(--font-mono); color: var(--ink-2); }
.col-risk   { width: 160px; color: var(--ink-2); }
.col-owner  { width: 140px; color: var(--ink-2); }
.col-id, .col-owner, .col-risk { font-size: 0.8125rem; }
.id-truncate { display: inline-block; max-width: 9ch; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.title-cell { color: var(--ink-1); }
.suggest-cell { color: var(--ink-2); font-size: 0.8125rem; }
.severity-glyph {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-right: var(--space-2);
  vertical-align: middle;
}
.sev-high { background: var(--state-crit); }
.sev-medium { background: var(--state-warn); }
.sev-low { background: var(--state-ok); }

/* ── Action group ── */
.action-group { margin-top: var(--space-5); }
.action-group + .action-group { margin-top: var(--space-6); }
.action-group-head {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink-2);
  margin-bottom: var(--space-3);
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
}
.action-group-head .count { color: var(--accent); }
.action-item {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--bg-rule);
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: var(--space-3);
}
.action-item:last-child { border-bottom: none; }
.action-item .id { font-family: var(--font-mono); color: var(--ink-2); font-size: 0.8125rem; padding-top: 2px; }
.action-item .title { color: var(--ink-1); }
.action-item .meta { margin-top: var(--space-1); font-family: var(--font-mono); font-size: 0.75rem; color: var(--ink-3); }

/* ── Footer ── */
.dash-footer {
  margin-top: var(--space-8);
  padding-top: var(--space-5);
  border-top: 1px solid var(--bg-rule);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}
.empty-state {
  padding: var(--space-7) 0;
  text-align: center;
  font-family: var(--font-mono);
  color: var(--ink-3);
  font-size: 0.875rem;
}
.overflow-note {
  margin-top: var(--space-3);
  padding: var(--space-2) 0;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--ink-3);
  letter-spacing: 0.02em;
  text-align: right;
  border-top: 1px dashed var(--bg-rule);
}

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}

/* ── Responsive ── */
@media (max-width: 1023px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .stat:nth-child(2) { border-right: none; }
  .stat:nth-child(1), .stat:nth-child(2) { border-bottom: 1px solid var(--bg-rule); }
  .col-owner, .col-suggest { display: none; }
}
@media (max-width: 639px) {
  main.dashboard { padding: var(--space-5) var(--space-3); }
  .stats { grid-template-columns: 1fr; }
  .stat { border-right: none; border-bottom: 1px solid var(--bg-rule); }
  .stat:last-child { border-bottom: none; }
  .dash-header h1 { font-size: 1.5rem; }
  table.risks thead { display: none; }
  table.risks tbody td { display: block; padding: var(--space-1) 0; border: none; }
  table.risks tbody tr {
    display: block;
    padding: var(--space-4) 0;
    border-bottom: 1px solid var(--bg-rule);
  }
  .col-status, .col-id, .col-risk, .col-owner { width: auto; }
  .action-item { grid-template-columns: 1fr; gap: var(--space-1); }
  .action-item .id { padding-top: 0; }
}
"""

_TEMPLATE = Template("""\
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MobiusPM · 630 攻坚大盘 · {{ date }}</title>
<style>{{ css }}</style>
</head>
<body>
<main class="dashboard" role="main">

<header class="dash-header">
  <h1>MobiusPM · 630 攻坚大盘</h1>
  <div class="meta">
    <span>{{ date }}</span>
    <span>{{ run_id }}</span>
    {% if db_path %}<span>{{ db_path }}</span>{% endif %}
  </div>
</header>

<section class="section dash-overview" aria-labelledby="sec-overview">
  <h2 id="sec-overview" class="section-title">项目总览</h2>
  <div class="stats" role="group" aria-label="项目统计指标">
    <div class="stat">
      <div class="stat-label">总数</div>
      <div class="stat-value">{{ stats.total }}</div>
      <div class="stat-meta">all items</div>
    </div>
    <div class="stat">
      <div class="stat-label">活跃</div>
      <div class="stat-value">{{ stats.active }}</div>
      <div class="stat-meta">open &amp; in progress</div>
    </div>
    <div class="stat">
      <div class="stat-label">已闭环</div>
      <div class="stat-value ok">{{ stats.closed }}</div>
      <div class="stat-meta">closed</div>
    </div>
    <div class="stat">
      <div class="stat-label">高风险</div>
      <div class="stat-value crit">{{ stats.high_risk }}</div>
      <div class="stat-meta">high severity</div>
    </div>
  </div>
</section>

<section class="section dash-risks" aria-labelledby="sec-risks">
  <h2 id="sec-risks" class="section-title">风险明细</h2>
  {% if risks %}
  <table class="risks">
    <thead>
      <tr>
        <th class="col-status">状态</th>
        <th class="col-id">ID</th>
        <th>标题</th>
        <th class="col-risk">风险类型</th>
        <th class="col-owner">责任人</th>
        <th class="col-suggest">建议</th>
      </tr>
    </thead>
    <tbody>
      {% for r in risks %}
      <tr>
        <td class="col-status">
          <span class="pill {{ r.pill_class }}" aria-label="{{ r.status_text }}">
            <span class="pill-glyph" aria-hidden="true">{{ r.glyph }}</span>
            <span>{{ r.status_text }}</span>
          </span>
        </td>
        <td class="col-id"><span class="id-truncate mono" title="{{ r.item_id }}">{{ r.item_id_short }}</span></td>
        <td class="title-cell">{{ r.title }}</td>
        <td class="col-risk"><span class="severity-glyph sev-{{ r.severity }}" aria-hidden="true"></span>{{ r.risk_type }}</td>
        <td class="col-owner">{{ r.owner }}</td>
        <td class="col-suggest suggest-cell">{{ r.suggest }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if risk_overflow > 0 %}
  <div class="overflow-note">还有 {{ risk_overflow }} 项风险未显示，按优先级展开 top {{ risks|length }}</div>
  {% endif %}
  {% else %}
  <div class="empty-state">无风险事项</div>
  {% endif %}
</section>

<section class="section dash-actions" aria-labelledby="sec-actions">
  <h2 id="sec-actions" class="section-title">建议行动</h2>
  {% if action_groups %}
    {% for g in action_groups %}
    <div class="action-group">
      <div class="action-group-head">
        <span>{{ g.label }}</span>
        <span class="count">{{ g.count }} 项</span>
      </div>
      {% for a in g.actions %}
      <div class="action-item">
        <span class="id id-truncate mono" title="{{ a.item_id }}">{{ a.item_id_short }}</span>
        <div>
          <div class="title">{{ a.title }}</div>
          <div class="meta">{{ a.owner }} · {{ a.context }}</div>
        </div>
      </div>
      {% endfor %}
      {% if g.overflow %}
      <div class="overflow-note">本组还有更多同类项未显示</div>
      {% endif %}
    </div>
    {% endfor %}
  {% else %}
  <div class="empty-state">本周期无需额外行动</div>
  {% endif %}
</section>

<footer class="dash-footer">
  <span>generated by pm_agent</span>
  <span> · {{ generated_at }}</span>
  <span> · {{ item_count }} work items · {{ suggest_count }} suggestions</span>
</footer>

</main>
</body>
</html>
""")


# ── 状态映射 ──

_STATUS_MAP = {
    "R-001": ("待验收", "■", "pill-warn", "high", "待验收"),
    "R-002": ("完成待关闭", "■", "pill-warn", "medium", "待关闭"),
    "R-003": ("开发中超期", "●", "pill-crit", "high", "超期"),
    "R-004": ("开发中临期", "▲", "pill-warn", "medium", "临期"),
    "R-005": ("待排期", "▲", "pill-warn", "high", "待排期"),
    "R-007": ("催办无响应", "●", "pill-crit", "high", "催办无响应"),
    "R-008": ("状态停滞", "▲", "pill-warn", "medium", "停滞"),
    "R-009": ("状态回退", "●", "pill-crit", "high", "回退"),
    "R-010": ("反复催办", "●", "pill-crit", "medium", "反复催办"),
    "DQ-001": ("缺责任人", "✕", "pill-mute", "medium", "缺责任人"),
    "DQ-002": ("负载过重", "▲", "pill-warn", "medium", "负载过重"),
    "DQ-003": ("缺截止日期", "▲", "pill-warn", "medium", "缺日期"),
}

_REMINDER_LABEL = {
    "acceptance_confirm": "ACCEPTANCE_CONFIRM",
    "close_confirm": "CLOSE_CONFIRM",
    "progress_check": "PROGRESS_CHECK",
    "schedule_confirm": "SCHEDULE_CONFIRM",
    "due_date_missing": "DUE_DATE_MISSING",
    "data_quality": "DATA_QUALITY",
    "escalation": "ESCALATION",
    "stagnation_alert": "STAGNATION",
    "regression_alert": "REGRESSION",
}


_RISK_TABLE_LIMIT = 30
_ACTION_GROUP_LIMIT = 8
_ACTION_ITEM_LIMIT = 8


def _build_risks(suggestions: list[dict], work_items: list[dict]) -> list[dict]:
    """从建议 + WorkItem 构建风险列表（按优先级排序）。"""
    items_by_id = {it["item_id"]: it for it in work_items}

    # 优先级权重：数字越小越靠前
    # 真风险（R-*）优先于数据质量（DQ-*）；超期/回退/催办无响应/反复催办最优先
    rule_priority = {
        "R-009": 0,  # 状态回退
        "R-007": 1,  # 催办无响应
        "R-003": 2,  # 开发中超期
        "R-010": 3,  # 反复催办
        "R-005": 4,  # 待排期
        "R-001": 5,  # 待验收
        "DQ-001": 6, # 缺责任人（数据质量，但阻塞后续流程）
        "R-002": 7,  # 完成待关闭
        "R-004": 8,  # 临期
        "R-008": 9,  # 状态停滞
        "DQ-003": 10, # 缺日期
        "DQ-002": 11, # 负载过重
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

    risks = []
    for s in sorted_sugg:
        if s["severity"] == "low":
            continue  # 看板只显示 high + medium
        rule_id = s["rule_id"]
        status_text, glyph, pill_cls, _map_sev, status_label = _STATUS_MAP.get(
            rule_id,
            ("其他", "■", "pill-mute", s["severity"], rule_id),
        )
        # severity 直接用 suggestion 的真实严重度（规则引擎已分级）
        sev = s["severity"]
        item = items_by_id.get(s["item_id"], {})
        owner_list = item.get("owner_list") or []
        owner = "/".join(owner_list) if owner_list else "未指派"
        title = item.get("title", s.get("rationale_hint", "")) or ""
        item_id = s["item_id"]

        # 风险类型：组合 rule_id 含义
        risk_type = {
            "R-001": "超期+待验收" if item.get("due_date") else "待验收",
            "R-002": "完成待关闭",
            "R-003": "超期+开发中",
            "R-004": "临期+开发中",
            "R-005": "待排期",
            "R-007": "催办无响应",
            "R-008": "状态停滞",
            "R-009": "状态回退",
            "R-010": "反复催办",
            "DQ-001": "缺责任人",
            "DQ-002": "负载过重",
            "DQ-003": "缺截止日期",
        }.get(rule_id, rule_id)

        risks.append({
            "item_id": item_id,
            "item_id_short": item_id[:8],
            "title": title,
            "owner": owner,
            "status_text": status_label,
            "glyph": glyph,
            "pill_class": pill_cls,
            "severity": sev,
            "risk_type": risk_type,
            "suggest": s.get("rationale_hint", ""),
            "rule_id": rule_id,
            "reminder_type": s.get("reminder_type", ""),
            "_owner_list": owner_list,
        })

    return risks


def _build_action_groups(
    suggestions: list[dict],
    risks: list[dict],
    work_items: list[dict],
) -> list[dict]:
    """按 reminder_type 分组建议行动。"""
    items_by_id = {it["item_id"]: it for it in work_items}
    risks_by_id = {r["item_id"]: r for r in risks}

    # 用 risks 已富集的数据 + suggestions 补全
    bucket: dict[str, list[dict]] = {}
    for r in risks:
        rt = r["reminder_type"] or "progress_check"
        bucket.setdefault(rt, []).append(r)

    groups = []
    for rt, items in bucket.items():
        label = _REMINDER_LABEL.get(rt, rt.upper())
        action_items = []
        for r in items:
            item = items_by_id.get(r["item_id"], {})
            owner_list = item.get("owner_list") or []
            owner = "/".join(owner_list) if owner_list else "未指派"

            # 上下文信息
            ctx_parts = []
            status = item.get("normalized_status") or ""
            due = item.get("due_date") or ""
            if status:
                ctx_parts.append(status)
            if due:
                ctx_parts.append(f"截止 {due}")
            # 加 risk_type 作为补充
            if r.get("risk_type"):
                ctx_parts.append(r["risk_type"])
            ctx = " · ".join(ctx_parts) or r.get("suggest", "")

            action_items.append({
                "item_id": r["item_id"],
                "item_id_short": r["item_id"][:8],
                "title": r["title"] or "(无标题)",
                "owner": owner,
                "context": ctx,
            })

        groups.append({
            "label": label,
            "count": len(action_items),
            "actions": action_items,
        })

    # 按数量倒序排列
    groups.sort(key=lambda g: g["count"], reverse=True)
    return groups


def _build_stats(work_items: list[dict], suggestions: list[dict]) -> dict:
    """汇总统计数字。"""
    total = len(work_items)
    closed_statuses = {"已关闭", "重复", "拒绝"}
    active = sum(1 for it in work_items if it.get("normalized_status") not in closed_statuses)
    closed = total - active
    high_risk = sum(1 for s in suggestions if s["severity"] == "high")
    return {
        "total": total,
        "active": active,
        "closed": closed,
        "high_risk": high_risk,
    }


def write_html_dashboard(
    work_items: list[dict],
    run_id: str,
    db_path: str | Path | None = None,
    output_dir: str | Path = _DASHBOARD_DIR,
) -> dict:
    """
    生成项目大盘 HTML 看板（自包含单文件）。

    输入：
        work_items: read_excel 返回的 WorkItem 列表
        run_id: 本次运行 ID
        db_path: SQLite 路径（可选，提供则启用历史依赖规则 R-007~R-010）
        output_dir: 输出目录（默认 state/dashboards）

    输出：
        {"status": "ok", "path": str, "size_bytes": int}
    """
    if not work_items:
        return {"status": "error", "reason": "work_items 为空"}

    # 1) 规则扫描
    result = query_rule_suggestions(work_items, db_path=db_path)
    suggestions = result["suggestions"]

    # 2) 渲染数据
    stats = _build_stats(work_items, suggestions)
    all_risks = _build_risks(suggestions, work_items)
    risks = all_risks[:_RISK_TABLE_LIMIT]
    risk_overflow = len(all_risks) - len(risks)
    all_groups = _build_action_groups(suggestions, all_risks, work_items)
    action_groups = all_groups[:_ACTION_GROUP_LIMIT]
    for g in action_groups:
        if len(g["actions"]) > _ACTION_ITEM_LIMIT:
            g["actions"] = g["actions"][:_ACTION_ITEM_LIMIT]
            g["overflow"] = True
        else:
            g["overflow"] = False

    # 3) 渲染 HTML
    now = datetime.now(timezone.utc)
    ctx = {
        "css": _CSS,
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "run_id": run_id,
        "db_path": str(db_path) if db_path else "",
        "stats": stats,
        "risks": risks,
        "risk_overflow": risk_overflow,
        "action_groups": action_groups,
        "item_count": len(work_items),
        "suggest_count": len(suggestions),
    }
    html = _TEMPLATE.render(**ctx)

    # 4) 写盘
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{now.strftime('%Y-%m-%d')}_{run_id}.html"
    out_path = output_dir / file_name
    out_path.write_text(html, encoding="utf-8")

    return {
        "status": "ok",
        "path": str(out_path),
        "size_bytes": out_path.stat().st_size,
        "stats": stats,
    }