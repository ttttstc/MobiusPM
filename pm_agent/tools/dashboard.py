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
.severity-glyph.sev-high { background: var(--state-crit); }
.severity-glyph.sev-medium { background: var(--state-warn); }
.severity-glyph.sev-low { background: var(--state-ok); }

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

/* ── Risk summary ── */
.summary-block {
  border: 1px solid var(--bg-rule);
  background: var(--bg-elev);
  padding: var(--space-5);
}
.summary-headline {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-wrap: wrap;
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--bg-rule);
  margin-bottom: var(--space-4);
}
.health-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  font-family: var(--font-mono);
  font-size: 0.875rem;
  font-weight: 600;
  border: 1px solid currentColor;
  white-space: nowrap;
}
.summary-narrative {
  font-size: 0.9375rem;
  line-height: 1.55;
  color: var(--ink-1);
  flex: 1 1 320px;
}
.summary-subtitle {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: var(--space-3);
}
.concern-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.concern-list li {
  padding: var(--space-2) 0;
  display: grid;
  grid-template-columns: 80px 1fr auto;
  gap: var(--space-3);
  align-items: baseline;
  border-bottom: 1px solid var(--bg-rule);
  font-size: 0.875rem;
}
.concern-list li:last-child { border-bottom: none; }
.concern-tag {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--accent);
  letter-spacing: 0.02em;
}
.concern-title { color: var(--ink-1); }
.concern-meta {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--ink-3);
}
.observation-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.observation-list li {
  padding: var(--space-2) 0 var(--space-2) var(--space-5);
  position: relative;
  font-size: 0.8125rem;
  color: var(--ink-2);
  border-bottom: 1px dashed var(--bg-rule);
}
.observation-list li:last-child { border-bottom: none; }
.observation-list li::before {
  content: "▸";
  position: absolute;
  left: 0;
  color: var(--accent);
  font-family: var(--font-mono);
}

/* ── Risk row severity ── */
table.risks tbody tr.risk-row.sev-high {
  background: var(--bg-elev);
}
table.risks tbody tr.risk-row.sev-high:hover {
  background: var(--bg-hover);
}
.col-rank { width: 36px; text-align: center; }
.rank-badge {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
  padding: 4px 6px;
  background: var(--accent);
  color: var(--bg);
  letter-spacing: 0;
}
.rank-badge.rank-1 { background: oklch(70% 0.22 25); color: var(--bg); }
.rank-badge.rank-2 { background: oklch(74% 0.20 45); color: var(--bg); }
.rank-badge.rank-3 { background: oklch(78% 0.18 75); color: var(--bg); }
.rank-badge.rank-4 { background: oklch(72% 0.14 95); color: var(--bg); }
.rank-badge.rank-5 { background: oklch(74% 0.12 110); color: var(--bg); }

.title-text {
  color: var(--ink-1);
  font-weight: 500;
  line-height: 1.4;
}
.remark-text {
  margin-top: var(--space-1);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--ink-3);
  padding-left: var(--space-3);
  border-left: 1px solid var(--bg-rule);
  line-height: 1.45;
}
.impact-cell { font-size: 0.8125rem; line-height: 1.5; }
.impact-line {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  margin-top: var(--space-2);
  flex-wrap: wrap;
}
.impact-label {
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--accent);
  flex-shrink: 0;
  white-space: nowrap;
}
.impact-text {
  font-size: 0.8125rem;
  color: var(--ink-1);
  line-height: 1.5;
}
.col-action { min-width: 280px; }
.col-impact { width: 220px; }
@media (min-width: 1024px) {
  .col-impact, .col-action { white-space: normal; }
}
.category-tag {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border: 1px solid var(--bg-rule);
  color: var(--ink-2);
  background: var(--bg);
  margin-right: var(--space-1);
  margin-bottom: 2px;
}
.category-tag.cat-schedule { color: oklch(78% 0.16 35); border-color: oklch(45% 0.10 35); }
.category-tag.cat-scope { color: oklch(80% 0.14 80); border-color: oklch(45% 0.08 80); }
.category-tag.cat-quality { color: oklch(82% 0.14 50); border-color: oklch(50% 0.08 50); }
.category-tag.cat-resource { color: oklch(78% 0.16 200); border-color: oklch(45% 0.10 200); }
.category-tag.cat-dependency { color: oklch(78% 0.16 290); border-color: oklch(45% 0.10 290); }
.category-tag.cat-stakeholder { color: oklch(80% 0.14 145); border-color: oklch(45% 0.08 145); }
.category-tag.cat-data { color: var(--ink-3); }

/* ── Advisory section ── */
.dash-advisories .advisory-note {
  margin-bottom: var(--space-4);
  padding: var(--space-3) var(--space-4);
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  color: var(--ink-3);
  background: var(--bg-elev);
  border-left: 1px solid var(--bg-rule);
}
.dash-advisories .advisory-note strong { color: var(--ink-2); }
table.advisories {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
  opacity: 0.85;
}
table.advisories thead th {
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
table.advisories tbody td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--bg-rule);
  vertical-align: top;
}
table.advisories tbody tr:hover { background: var(--bg-hover); }

/* ── Reduced motion ── */
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}

/* ── Responsive ── */
@media (max-width: 1023px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .stat:nth-child(2) { border-right: none; }
  .stat:nth-child(1), .stat:nth-child(2) { border-bottom: 1px solid var(--bg-rule); }
  .col-owner, .col-suggest, .col-action { display: none; }
  .summary-headline { gap: var(--space-3); }
  .concern-list li { grid-template-columns: 70px 1fr; }
  .concern-meta { grid-column: 2; padding-left: 0; }
}
@media (max-width: 639px) {
  main.dashboard { padding: var(--space-5) var(--space-3); }
  .stats { grid-template-columns: 1fr; }
  .stat { border-right: none; border-bottom: 1px solid var(--bg-rule); }
  .stat:last-child { border-bottom: none; }
  .dash-header h1 { font-size: 1.5rem; }
  .summary-block { padding: var(--space-4); }
  .summary-headline { flex-direction: column; align-items: flex-start; }
  .summary-narrative { font-size: 0.875rem; }
  table.risks thead { display: none; }
  table.risks tbody td { display: block; padding: var(--space-1) 0; border: none; }
  table.risks tbody tr {
    display: block;
    padding: var(--space-4) 0;
    border-bottom: 1px solid var(--bg-rule);
  }
  .col-status, .col-id, .col-risk, .col-owner, .col-rank { width: auto; display: inline-block; margin-right: var(--space-2); }
  .col-rank { display: inline-block; }
  .title-text { font-size: 0.9375rem; }
  .remark-text { font-size: 0.75rem; }
  table.advisories thead { display: none; }
  table.advisories tbody td { display: block; padding: var(--space-1) 0; border: none; }
  table.advisories tbody tr {
    display: block;
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--bg-rule);
  }
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

<section class="section dash-summary" aria-labelledby="sec-summary">
  <h2 id="sec-summary" class="section-title">总体风险总结（PM 视角）</h2>
  <div class="summary-block">
    <div class="summary-headline">
      <span class="health-pill pill-{{ risk_summary.health_class }}" aria-label="整体健康度">
        <span class="pill-glyph" aria-hidden="true">{{ risk_summary.health_glyph }}</span>
        <span>{{ risk_summary.health_label }}</span>
      </span>
      <span class="summary-narrative">{{ risk_summary.narrative }}</span>
    </div>

    {% if risk_summary.top_concerns %}
    <div class="summary-concerns">
      <div class="summary-subtitle">今日必须处置（TOP 3）</div>
      <ol class="concern-list">
        {% for c in risk_summary.top_concerns %}
        <li>
          <span class="concern-tag" aria-hidden="true">[{{ c.rule_id }}]</span>
          <span class="concern-title">
            <span class="category-tag cat-{{ c.category_class }}" aria-label="风险类别">{{ c.category }}</span>
            {{ c.title }}
            <div class="impact-line">
              <span class="impact-label">影响</span>
              <span class="impact-text">{{ c.impact }}</span>
            </div>
            <div class="impact-line">
              <span class="impact-label">24h 动作</span>
              <span class="impact-text">{{ c.next_action }}</span>
            </div>
            <div class="impact-line">
              <span class="impact-label">升级路径</span>
              <span class="impact-text">{{ c.escalation }}</span>
            </div>
          </span>
          <span class="concern-meta">{{ c.tag }} · {{ c.owner }}</span>
        </li>
        {% endfor %}
      </ol>
    </div>
    {% endif %}

    {% if risk_summary.observations %}
    <div class="summary-observations">
      <div class="summary-subtitle">关键观察</div>
      <ul class="observation-list">
        {% for o in risk_summary.observations %}
        <li>{{ o }}</li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}
  </div>
</section>

<section class="section dash-risks" aria-labelledby="sec-risks">
  <h2 id="sec-risks" class="section-title">风险明细</h2>
  {% if risks %}
  <table class="risks">
    <thead>
      <tr>
        <th class="col-rank">#</th>
        <th class="col-status">状态</th>
        <th class="col-id">ID</th>
        <th>标题 / 备注</th>
        <th class="col-impact">影响</th>
        <th class="col-action">24h 动作 / 升级路径</th>
      </tr>
    </thead>
    <tbody>
      {% for r in risks %}
      <tr class="risk-row sev-{{ r.severity }}{% if r.priority_rank %} is-top{{ r.priority_rank }}{% endif %}">
        <td class="col-rank">
          {% if r.priority_rank %}<span class="rank-badge rank-{{ r.priority_rank }}">{{ r.priority_rank }}</span>{% endif %}
        </td>
        <td class="col-status">
          <span class="pill {{ r.pill_class }}" aria-label="{{ r.status_text }}">
            <span class="pill-glyph" aria-hidden="true">{{ r.glyph }}</span>
            <span>{{ r.status_text }}</span>
          </span>
        </td>
        <td class="col-id"><span class="id-truncate mono" title="{{ r.item_id }}">{{ r.item_id_short }}</span></td>
        <td class="title-cell">
          <div class="title-text"><span class="category-tag cat-{{ r.category_class }}" aria-label="风险类别">{{ r.category }}</span>{{ r.title }}</div>
          {% if r.remark %}<div class="remark-text">{{ r.remark }}</div>{% endif %}
        </td>
        <td class="col-impact impact-cell">
          <div>{{ r.impact }}</div>
          <div class="impact-line">
            <span class="concern-meta">责任人 · {{ r.owner }}</span>
          </div>
        </td>
        <td class="col-action impact-cell">
          <div class="impact-line">
            <span class="impact-label">24h</span>
            <span class="impact-text">{{ r.next_action }}</span>
          </div>
          <div class="impact-line">
            <span class="impact-label">升级</span>
            <span class="impact-text">{{ r.escalation }}</span>
          </div>
        </td>
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

{% if advisories %}
<section class="section dash-advisories" aria-labelledby="sec-advisories">
  <h2 id="sec-advisories" class="section-title">提示事项（非高风险，仅供参考）</h2>
  <div class="advisory-note">以下事项处于正常流程状态（如待验收），不属于紧急风险。如需跟催请走 <strong>建议行动</strong> 章节。</div>
  <table class="advisories">
    <thead>
      <tr>
        <th class="col-id">ID</th>
        <th>标题</th>
        <th class="col-status">状态</th>
        <th class="col-owner">责任人</th>
      </tr>
    </thead>
    <tbody>
      {% for a in advisories %}
      <tr>
        <td class="col-id"><span class="id-truncate mono" title="{{ a.item_id }}">{{ a.item_id_short }}</span></td>
        <td class="title-cell">{{ a.title }}</td>
        <td class="col-status">
          <span class="pill {{ a.pill_class }}" aria-label="{{ a.status_text }}">
            <span class="pill-glyph" aria-hidden="true">{{ a.glyph }}</span>
            <span>{{ a.status_text }}</span>
          </span>
        </td>
        <td class="col-owner">{{ a.owner }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if advisory_overflow > 0 %}
  <div class="overflow-note">还有 {{ advisory_overflow }} 项提示事项未显示</div>
  {% endif %}
</section>
{% endif %}

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
    "R-001": ("待验收", "■", "pill-mute", "low", "待验收"),  # 提示项，非高风险
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
_ADVISORY_LIMIT = 50
_ACTION_GROUP_LIMIT = 8
_ACTION_ITEM_LIMIT = 8

# 风险类型分类（按 rule_id 映射）
_RISK_TYPE_LABEL = {
    "R-001": lambda it: "超期+待验收" if it.get("due_date") else "待验收",
    "R-002": lambda it: "完成待关闭",
    "R-003": lambda it: "超期+开发中",
    "R-004": lambda it: "临期+开发中",
    "R-005": lambda it: "待排期",
    "R-007": lambda it: "催办无响应",
    "R-008": lambda it: "状态停滞",
    "R-009": lambda it: "状态回退",
    "R-010": lambda it: "反复催办",
    "DQ-001": lambda it: "缺责任人",
    "DQ-002": lambda it: "负载过重",
    "DQ-003": lambda it: "缺截止日期",
}

# PM 风险类别（不直接用规则 ID 跟 PM 沟通）
# 进度 / 范围 / 质量 / 资源 / 依赖 / 干系人 / 数据质量
_RISK_CATEGORY = {
    "R-001": ("进度", "schedule"),
    "R-002": ("质量", "quality"),
    "R-003": ("进度", "schedule"),
    "R-004": ("进度", "schedule"),
    "R-005": ("范围", "scope"),
    "R-007": ("依赖", "dependency"),
    "R-008": ("进度", "schedule"),
    "R-009": ("质量", "quality"),
    "R-010": ("依赖", "dependency"),
    "DQ-001": ("资源", "resource"),
    "DQ-002": ("资源", "resource"),
    "DQ-003": ("范围", "scope"),
}

# 24h 动作模板（避免"催办"空话）
_NEXT_ACTION = {
    "R-001": lambda it: "今天联系责任人确认验收进展；如有阻塞找 Owner 拉群对账",
    "R-002": lambda it: "今天内确认是否可以关闭；否则转 PM 决策延期",
    "R-003": lambda it: "今天 17:00 前拉群对齐进度；如阻塞找 Sponsor 升级",
    "R-004": lambda it: "今天确认剩余工作量；明天前给出可完成节点",
    "R-005": lambda it: "今天拉强制排期会议；产出明确责任人 + 时间",
    "R-007": lambda it: "今天通过 Sponsor 渠道升级；同步测试/上下游团队",
    "R-008": lambda it: "今天确认事项状态；停滞 >30 天的重新评估优先级",
    "R-009": lambda it: "今天做根因分析；曾闭环又出现需 Sponsor 介入",
    "R-010": lambda it: "今天评估升级或调整策略；≥2 次同类型催办建议重新指定 Owner",
    "DQ-001": lambda it: "今天指派 Owner；标注为不可催办，需人工分配",
    "DQ-002": lambda it: "今天评估负载再分配；考虑加 Owner 或延期",
    "DQ-003": lambda it: "今天补录计划时间；P0/P1 必须有截止日期",
}

# 升级路径（给出明确路径而不是"建议升级"）
_ESCALATION_PATH = {
    "R-001": "Owner → PM",
    "R-002": "Owner → PM",
    "R-003": "Owner → Sponsor（影响 630 节点）",
    "R-004": "Owner → PM",
    "R-005": "PM 强制排期会议",
    "R-007": "Owner → Sponsor → 跨团队 Sponsor",
    "R-008": "Owner → PM（重新评估优先级）",
    "R-009": "PM → Sponsor（根因分析）",
    "R-010": "PM 评估 → 调整 Owner 或重定策略",
    "DQ-001": "PM 手动指派（不可自动催）",
    "DQ-002": "PM 评估负载再分配",
    "DQ-003": "PM 补录或降级优先级",
}


def _enrich_suggestion(
    s: dict, items_by_id: dict, items_index: dict | None = None
) -> dict:
    """把建议 + WorkItem 富集为统一结构（含 remark / owner / risk_type / PM 类别等）。"""
    rule_id = s["rule_id"]
    item = items_by_id.get(s["item_id"], {})
    owner_list = item.get("owner_list") or []
    owner = "/".join(owner_list) if owner_list else "未指派"
    title = item.get("title", "") or s.get("rationale_hint", "")
    remark = item.get("remark") or ""

    # 状态映射 — R-001 按 reminder_type 区分（acceptance → 待验收/提示，close → 待关闭/风险）
    reminder_type = s.get("reminder_type", "")
    status_text, glyph, pill_cls, _map_sev, status_label = ("其他", "■", "pill-mute", s["severity"], rule_id)
    if rule_id == "R-001" and reminder_type == "close_confirm":
        status_text, glyph, pill_cls = "待关闭", "●", "pill-warn"
        status_label = "待关闭"
    else:
        status_text, glyph, pill_cls, _map_sev, status_label = _STATUS_MAP.get(
            rule_id,
            ("其他", "■", "pill-mute", s["severity"], rule_id),
        )

    # 风险类型
    type_fn = _RISK_TYPE_LABEL.get(rule_id)
    risk_type = type_fn(item) if type_fn else rule_id

    # PM 风险类别（进度/范围/质量/资源/依赖/干系人/数据质量）
    cat_label, cat_class = _RISK_CATEGORY.get(rule_id, ("数据质量", "data"))

    # 24h 动作（基于规则 + WorkItem 上下文）
    action_fn = _NEXT_ACTION.get(rule_id)
    next_action = action_fn(item) if action_fn else "今天联系责任人确认状态"

    # 升级路径
    escalation = _ESCALATION_PATH.get(rule_id, "Owner → PM")

    # 影响描述（PM 视角，不是"超期"而是"对 630 的影响"）
    impact = _build_impact_text(rule_id, item)

    return {
        "item_id": s["item_id"],
        "item_id_short": s["item_id"][:8],
        "title": title,
        "owner": owner,
        "owner_list": owner_list,
        "remark": remark,
        "status_text": status_label,
        "glyph": glyph,
        "pill_class": pill_cls,
        "severity": s["severity"],
        "risk_type": risk_type,
        "category": cat_label,
        "category_class": cat_class,
        "next_action": next_action,
        "escalation": escalation,
        "impact": impact,
        "suggest": s.get("rationale_hint", ""),
        "rule_id": rule_id,
        "reminder_type": s.get("reminder_type", ""),
        "due_date": item.get("due_date"),
        "status": item.get("normalized_status", ""),
        "priority": item.get("priority_level", ""),
    }


def _build_impact_text(rule_id: str, item: dict) -> str:
    """构建 PM 视角的影响描述（说明对 630 节点的具体影响）。"""
    priority = item.get("priority_level", "")
    status = item.get("normalized_status", "")
    due = item.get("due_date") or ""

    if rule_id == "R-003":  # 开发中超期
        if priority == "P0":
            return "P0 已超期，直接阻塞 630 节点；今天必须升级"
        return f"开发中超期 ({due or '无日期'})，影响后续依赖"
    if rule_id == "R-004":  # 临期
        return f"{priority} 临期 ({due})，需确认是否可按时完成"
    if rule_id == "R-005":  # 待排期
        return f"{priority} 待排期，无法评估对 630 的影响，需立即排期"
    if rule_id == "R-007":  # 催办无响应
        return f"已催办无响应，{priority} 阻塞下游 / 跨团队协作"
    if rule_id == "R-009":  # 状态回退
        return "曾闭环事项重新出现，需根因分析；可能影响范围声明"
    if rule_id == "R-010":  # 反复催办
        return "反复催办无效，建议升级或调整策略 / Owner"
    if rule_id == "R-008":  # 状态停滞
        return f"状态长期不变，{priority} 风险累积"
    if rule_id == "DQ-001":
        return "缺责任人，无法自动跟催；需 PM 手动指派"
    if rule_id == "DQ-002":
        return "责任人负载过重，建议评估再分配或延期"
    if rule_id == "DQ-003":
        return f"{priority} 缺截止日期，无法评估进度风险"
    if rule_id == "R-002":
        return "已完成但 Open，需确认状态后可关闭"
    return f"{priority} {status or '事项'} 需关注"


def _build_risks(suggestions: list[dict], work_items: list[dict]) -> list[dict]:
    """从建议 + WorkItem 构建风险列表（仅 high + medium，按优先级排序）。"""
    items_by_id = {it["item_id"]: it for it in work_items}

    # 优先级权重：真风险（R-*）优先于数据质量（DQ-*）
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

    risks = []
    for s in sorted_sugg:
        if s["severity"] == "low":
            continue  # 提示项走另一通路
        enriched = _enrich_suggestion(s, items_by_id)
        risks.append(enriched)

    return risks


def _build_advisories(suggestions: list[dict], work_items: list[dict]) -> list[dict]:
    """构建提示项列表（仅 low severity，含 R-001 待验收）。"""
    items_by_id = {it["item_id"]: it for it in work_items}

    sorted_sugg = sorted(
        (s for s in suggestions if s["severity"] == "low"),
        key=lambda s: (s["rule_id"], s["item_id"]),
    )

    advisories = []
    for s in sorted_sugg:
        enriched = _enrich_suggestion(s, items_by_id)
        advisories.append(enriched)

    return advisories


def _build_risk_summary(
    work_items: list[dict],
    suggestions: list[dict],
    all_risks: list[dict],
) -> dict:
    """构建总体风险总结 section。

    包括：整体健康度（PM 视角） + Top 3 关键关注 + 关键观察
    """
    from datetime import date

    total = len(work_items)
    high = sum(1 for s in suggestions if s["severity"] == "high")
    medium = sum(1 for s in suggestions if s["severity"] == "medium")
    low = sum(1 for s in suggestions if s["severity"] == "low")

    # 超期计算
    today = date.today().isoformat()
    overdue_items = [
        it for it in work_items
        if it.get("due_date") and it.get("due_date") < today
        and it.get("normalized_status") not in ("已关闭", "挂起", "重复", "拒绝")
    ]
    overdue_count = len(overdue_items)

    # PM 风险类别分布
    category_breakdown: dict[str, int] = {}
    for r in all_risks:
        cat = r.get("category", "其他")
        category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

    # 整体健康度（PM 视角：基于 high 比例 + overdue 比例 + 类别分布）
    high_ratio = high / total if total else 0
    overdue_ratio = overdue_count / total if total else 0
    has_regression = any(s["rule_id"] == "R-009" for s in suggestions)
    has_no_response = any(s["rule_id"] == "R-007" for s in suggestions)
    has_p0_overdue = any(
        it.get("priority_level") == "P0" and it.get("due_date") and it.get("due_date") < today
        and it.get("normalized_status") not in ("已关闭", "挂起", "重复", "拒绝")
        for it in work_items
    )

    if high_ratio > 0.25 or overdue_ratio > 0.10 or has_p0_overdue:
        health_label = "高危冲刺"
        health_glyph = "●"
        health_class = "crit"
    elif high_ratio > 0.10 or overdue_ratio > 0.05 or has_no_response:
        health_label = "中等风险"
        health_glyph = "▲"
        health_class = "warn"
    else:
        health_label = "整体可控"
        health_glyph = "■"
        health_class = "ok"

    # Top 3 关键关注（按优先级 + PM 影响）
    top_concerns = []
    seen_ids = set()
    for r in all_risks:
        if r["item_id"] in seen_ids:
            continue
        seen_ids.add(r["item_id"])
        top_concerns.append({
            "title": r["title"],
            "tag": r["status_text"],
            "owner": r["owner"],
            "rule_id": r["rule_id"],
            "category": r.get("category", ""),
            "category_class": r.get("category_class", "data"),
            "impact": r.get("impact", ""),
            "next_action": r.get("next_action", ""),
            "escalation": r.get("escalation", ""),
        })
        if len(top_concerns) >= 3:
            break

    # 关键观察（PM 视角）
    observations = []
    if has_p0_overdue:
        observations.append("P0 已超期且未闭环，今天必须升级到 Sponsor")
    if overdue_count:
        observations.append(f"{overdue_count} 项已超期未闭环（不限于 P0）")
    if has_regression:
        observations.append("存在状态回退，曾闭环事项重新出现，需根因分析")
    if has_no_response:
        observations.append("存在催办无响应，建议通过 Sponsor 渠道升级")
    if category_breakdown.get("资源"):
        observations.append(f"资源类问题 {category_breakdown['资源']} 项（缺责任人 / 负载过重）")
    if category_breakdown.get("依赖"):
        observations.append(f"依赖类问题 {category_breakdown['依赖']} 项（跨团队阻塞）")
    if category_breakdown.get("范围"):
        observations.append(f"范围类问题 {category_breakdown['范围']} 项（待排期 / 缺日期）")

    narrative_parts = [
        f"项目整体处于【{health_label}】状态。",
        f"高风险 {high} 项 · 中风险 {medium} 项 · 提示项 {low} 项",
    ]
    if overdue_count:
        narrative_parts.append(f"超期 {overdue_count} 项")
    if category_breakdown:
        cat_str = " / ".join(f"{k} {v} 项" for k, v in sorted(category_breakdown.items(), key=lambda x: -x[1]))
        narrative_parts.append(f"风险类别分布：{cat_str}")
    narrative_parts.append("PM 应优先处理 P0 已超期、状态回退、催办无响应三类。")
    narrative = " · ".join(narrative_parts)

    return {
        "health_label": health_label,
        "health_glyph": health_glyph,
        "health_class": health_class,
        "narrative": narrative,
        "top_concerns": top_concerns,
        "observations": observations,
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
        "overdue_count": overdue_count,
        "category_breakdown": category_breakdown,
    }


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
    # 标记 top 5 优先级（用于视觉强调）
    for idx, r in enumerate(risks):
        r["priority_rank"] = idx + 1 if idx < 5 else None
    all_advisories = _build_advisories(suggestions, work_items)
    advisories = all_advisories[:_ADVISORY_LIMIT]
    advisory_overflow = len(all_advisories) - len(advisories)
    risk_summary = _build_risk_summary(work_items, suggestions, all_risks)
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
        "risk_summary": risk_summary,
        "risks": risks,
        "risk_overflow": risk_overflow,
        "advisories": advisories,
        "advisory_overflow": advisory_overflow,
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