"""write_project_report — 生成结构化项目巡检报告（PRD 要求）"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pm_agent.memory.store import DEFAULT_DB_PATH, Store

_REPORT_DIR = Path("state/reports")


def write_project_report(
    report_content: str,
    run_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    """
    写入结构化项目巡检报告 (markdown)。

    报告写入 state/reports/{date}_{run_id}.md，
    同时存一份摘要到 context_brief 作为跨周期记忆。

    report_content 应包含：项目总览、状态分布、风险诊断、趋势变化、建议行动。
    """
    report_content = (report_content or "").strip()
    if not report_content:
        return {"status": "error", "reason": "report_content 为空"}

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = _REPORT_DIR / f"{today}_{run_id}.md"

    # 写入报告文件
    report_path.write_text(report_content, encoding="utf-8")

    # 提取摘要存 brief（取前 500 字符作为摘要）
    summary = report_content[:500].replace("\n", " ").strip()
    if len(report_content) > 500:
        summary += "..."

    store = Store(db_path)
    try:
        store.insert_brief(
            run_id=run_id,
            brief=f"[报告] {summary}",
            token_count=len(report_content),
        )
        latest = store.get_latest_brief()
        brief_id = latest["id"] if latest else -1
    finally:
        store.close()

    return {
        "status": "ok",
        "report_path": str(report_path),
        "brief_id": brief_id,
        "char_count": len(report_content),
    }
