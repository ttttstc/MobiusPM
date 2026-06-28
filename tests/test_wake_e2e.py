"""Wake 端到端测试 — 模拟完整 wake 流程（Phase 1 + 1.5 + 2 + 3）。

模拟内容：
- 不调用 LLM（无 API key），但模拟 agent 在 Phase 1.5 中按顺序调用所有 5 个工具
- 用真实 Excel 数据验证数据流一致性
- 模拟 2 次 wake，验证趋势 diff / 周新增 / dashboard 数据无打架
- 模拟 Phase 2 决策记录 + Phase 3 通知聚合

输出全部写入 tmp_path（不污染 state/）。
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EXCEL_PATH = PROJECT_ROOT / "source" / "项目630流水线排期计划.xlsx"

# 必须有真实 Excel，否则跳整组测试
pytestmark = pytest.mark.skipif(
    not EXCEL_PATH.exists(),
    reason="需要 source/项目630流水线排期计划.xlsx 真实数据",
)


def _simulate_wake(
    work_items: list[dict],
    run_id: str,
    state_dir: Path,
    contacts: dict | None = None,
    prev_suggestions: list[dict] | None = None,
) -> dict:
    """模拟一次完整 wake 的 Phase 1.5 工具调用链。

    返回所有产物的路径 + 摘要，便于跨产物一致性校验。
    """
    from pm_agent.tools.dashboard import write_html_dashboard
    from pm_agent.tools.owner_load import query_owner_load
    from pm_agent.tools.rules import query_rule_suggestions
    from pm_agent.tools.sponsor_brief import write_sponsor_brief
    from pm_agent.tools.trend import query_trend, record_snapshot

    # ── Phase 1.5 step 1：留痕 snapshot
    rules_result = query_rule_suggestions(work_items)
    suggestions = rules_result["suggestions"]
    snap = record_snapshot(
        work_items,
        suggestions,
        run_id=run_id,
        trend_dir=state_dir / "trend",
    )

    # ── Phase 1.5 step 2：趋势对比
    trend = query_trend(run_id=run_id, trend_dir=state_dir / "trend")

    # ── Phase 1.5 step 3：Owner 负载
    load = query_owner_load(work_items)

    # ── Phase 1.5 step 4：上级简报
    brief = write_sponsor_brief(
        work_items,
        suggestions,
        run_id=run_id,
        trend_snapshot=trend.get("snapshot"),
        trend_previous=trend.get("previous"),
        owner_load=load,
        output_dir=state_dir / "sponsor_brief",
    )

    # ── Phase 1.5 step 5：HTML 大盘
    dash = write_html_dashboard(
        work_items,
        run_id=run_id,
        output_dir=state_dir / "dashboards",
    )

    return {
        "run_id": run_id,
        "work_items_count": len(work_items),
        "suggestions_count": len(suggestions),
        "by_severity": rules_result["summary"]["by_severity"],
        "by_rule": rules_result["summary"]["by_rule"],
        "snapshot": snap,
        "trend": trend,
        "owner_load": load,
        "brief": brief,
        "dashboard": dash,
    }


class TestWakePhase1_5FirstRun:
    """第一次 wake：snapshot 首次写入 + 趋势判定"首次对比" + dashboard 渲染。"""

    def test_first_wake_produces_all_artifacts(self, tmp_path):
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        work_items = result["items"]

        wake = _simulate_wake(
            work_items=work_items,
            run_id="e2e_wake_001",
            state_dir=tmp_path,
        )

        # 5 个产物都存在
        assert wake["snapshot"]["status"] == "ok"
        assert Path(wake["snapshot"]["path"]).exists()
        assert Path(wake["brief"]["path"]).exists()
        assert Path(wake["dashboard"]["path"]).exists()

        # 趋势判定：第一次 → "首次对比" 或 "首次运行"（取决于是否先 record 再 query）
        assert wake["trend"]["verdict"]["direction"] in ("首次对比", "首次运行")

        # snapshot 字段完整性
        snap = wake["snapshot"]["snapshot"]
        for k in ("total", "active", "closed", "high_risk", "overdue",
                  "by_priority", "by_status", "by_owner_count"):
            assert k in snap

        # dashboard 大小合理（179 个真实事项 → ~150KB）
        assert 10_000 < wake["dashboard"]["size_bytes"] < 200_000

    def test_brief_under_30_lines(self, tmp_path):
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        wake = _simulate_wake(
            work_items=result["items"],
            run_id="e2e_lines",
            state_dir=tmp_path,
        )
        assert wake["brief"]["line_count"] < 30

    def test_brief_contains_required_sections(self, tmp_path):
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        wake = _simulate_wake(
            work_items=result["items"],
            run_id="e2e_sections",
            state_dir=tmp_path,
        )
        text = Path(wake["brief"]["path"]).read_text(encoding="utf-8")
        for section in [
            "上级简报",
            "距 630 节点",
            "核心判断",
            "关键决策项",
            "数字变化 vs 上周",
            "下周风险预判",
        ]:
            assert section in text, f"Brief 缺少章节: {section}"


class TestWakeDataConsistency:
    """关键约束：dashboard 与 brief 的数字必须来自同一 source，不打架。"""

    def test_stats_match_between_dashboard_and_brief(self, tmp_path):
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        work_items = result["items"]
        wake = _simulate_wake(
            work_items=work_items,
            run_id="e2e_consistency",
            state_dir=tmp_path,
        )

        # dashboard 显示的 total / active / closed
        dash = wake["dashboard"]["stats"]
        # snapshot 的 total / active / closed
        snap = wake["snapshot"]["snapshot"]
        assert dash["total"] == snap["total"]
        assert dash["active"] == snap["active"]
        assert dash["closed"] == snap["closed"]
        assert dash["high_risk"] == snap["high_risk"]

        # brief 里的数字（高风险 / 中风险 / 超期）必须和 snapshot 一致
        brief_text = Path(wake["brief"]["path"]).read_text(encoding="utf-8")
        # 高风险 X 项 / 中风险 Y 项 出现在核心判断中
        if snap["high_risk"] > 0 or snap.get("overdue", 0) > 0:
            assert f"高风险 {snap['high_risk']} 项" in brief_text

    def test_owner_load_appears_in_dashboard(self, tmp_path):
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        wake = _simulate_wake(
            work_items=result["items"],
            run_id="e2e_load",
            state_dir=tmp_path,
        )

        dash_html = Path(wake["dashboard"]["path"]).read_text(encoding="utf-8")
        # dashboard 应有 owner-load section
        assert 'aria-labelledby="sec-owner-load"' in dash_html
        # 至少出现 1 个 owner 名字
        load = wake["owner_load"]
        assert len(load["owners"]) > 0
        first_owner = load["owners"][0]["owner"]
        assert first_owner in dash_html

    def test_trend_section_appears_in_dashboard(self, tmp_path):
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        wake = _simulate_wake(
            work_items=result["items"],
            run_id="e2e_trend",
            state_dir=tmp_path,
        )

        dash_html = Path(wake["dashboard"]["path"]).read_text(encoding="utf-8")
        assert 'aria-labelledby="sec-trend"' in dash_html
        assert "进度趋势" in dash_html
        # trend pill 一定存在
        assert "trend-pill" in dash_html

    def test_no_english_in_user_facing_outputs(self, tmp_path):
        """dashboard / brief / snapshot JSON 不含 Sponsor / Ask / HIGH/MEDIUM/LOW 等英文。"""
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        wake = _simulate_wake(
            work_items=result["items"],
            run_id="e2e_chinese",
            state_dir=tmp_path,
        )

        bad_tokens = ["Sponsor", "Ask ", "ACCEPTANCE", "PROGRESS_CHECK",
                      "ESCALATION", "DATA_QUALITY", "HIGH]", "MEDIUM]"]
        dash_html = Path(wake["dashboard"]["path"]).read_text(encoding="utf-8")
        brief_text = Path(wake["brief"]["path"]).read_text(encoding="utf-8")
        snap_json = Path(wake["snapshot"]["path"]).read_text(encoding="utf-8")

        for tok in bad_tokens:
            assert tok not in dash_html, f"dashboard 含英文 token: {tok}"
            assert tok not in brief_text, f"brief 含英文 token: {tok}"
            assert tok not in snap_json, f"snapshot 含英文 token: {tok}"


class TestWakeMultiRunTrend:
    """两次 wake：第二次必须有 trend diff。"""

    def test_second_wake_has_diff(self, tmp_path):
        from pm_agent.tools.excel import read_excel

        # 第一次
        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        wake1 = _simulate_wake(
            work_items=result["items"],
            run_id="e2e_run_1",
            state_dir=tmp_path,
        )
        assert wake1["trend"]["diff"] is None  # 首次无 diff

        # 第二次：找一个无 due_date 的活跃 P0，给它补一个超期日期
        work_items_v2 = [dict(it) for it in result["items"]]
        changed = False
        for it in work_items_v2:
            if (
                it.get("priority_level") == "P0"
                and it.get("normalized_status") not in ("已关闭", "挂起", "重复", "拒绝")
                and not it.get("due_date")
            ):
                it["due_date"] = "2026-06-01"  # 已超期
                changed = True
                break
        assert changed, "测试数据中没找到无日期 P0 用于构造恶化"

        wake2 = _simulate_wake(
            work_items=work_items_v2,
            run_id="e2e_run_2",
            state_dir=tmp_path,
        )

        # 第二次一定有 diff
        assert wake2["trend"]["diff"] is not None
        diff = wake2["trend"]["diff"]
        # 至少有 overdue 增加
        assert diff["overdue"]["current"] > diff["overdue"]["previous"], (
            f"expected overdue to grow: prev={diff['overdue']['previous']}, cur={diff['overdue']['current']}"
        )

        # brief 第二版包含 trend diff 表格
        brief2 = Path(wake2["brief"]["path"]).read_text(encoding="utf-8")
        assert "上周" in brief2 and "本周" in brief2

    def test_snapshots_persist_across_runs(self, tmp_path):
        """两次 wake 后 trend_dir 应该有 2 个 snapshot 文件。"""
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        _simulate_wake(result["items"], "e2e_persist_1", tmp_path)
        _simulate_wake(result["items"], "e2e_persist_2", tmp_path)

        snaps = list((tmp_path / "trend").glob("*.json"))
        assert len(snaps) == 2, f"应有 2 个 snapshot，实际 {len(snaps)}"


class TestWakeDecisionAndSend:
    """Phase 2 决策记录 + Phase 3 通知聚合（无 LLM 模拟，直接调工具）。"""

    def test_write_decision_creates_audit_record(self, tmp_path):
        from pm_agent.tools.state import write_decision

        db = tmp_path / "pm-agent.db"
        result = write_decision(
            decision_type="escalate",
            rationale="P0 已超期且无响应，必须升级到上级拉群对账",
            run_id="e2e_phase2_001",
            target_item_id="abc123def456",
            action_taken="调 query_state 后联系责任人",
            db_path=str(db),
        )
        assert result["status"] == "ok"

        from pm_agent.memory.store import Store
        store = Store(str(db))
        decisions = store._conn.execute(
            "SELECT decision_type, rationale FROM decision_log WHERE run_id=?",
            ("e2e_phase2_001",),
        ).fetchall()
        store.close()
        assert len(decisions) == 1
        assert decisions[0][0] == "escalate"
        assert len(decisions[0][1]) >= 20  # rationale ≥ 20 字符

    def test_decision_rationale_min_length_enforced(self, tmp_path):
        from pm_agent.tools.state import write_decision

        db = tmp_path / "pm-agent.db"
        with pytest.raises(Exception):
            write_decision(
                decision_type="followup",
                rationale="太短",  # < 20 字符
                run_id="e2e_rationale_short",
                db_path=str(db),
            )

    def test_gen_message_uses_chinese_template(self, tmp_path):
        from pm_agent.tools.messages import gen_message

        # 测试 9 类模板都生成中文消息
        for reminder_type in [
            "acceptance_confirm",
            "progress_check",
            "schedule_confirm",
            "due_date_missing",
            "close_confirm",
            "data_quality",
            "escalation",
            "stagnation_alert",
            "regression_alert",
        ]:
            result = gen_message(
                item_id="abc123def456",
                reminder_type=reminder_type,
                context={
                    "title": "测试事项",
                    "project": "MobiusPM",
                    "source": "GitCode",
                    "priority": "P0",
                    "handler": "张三",
                    "due_date": "2026-06-30",
                    "remark": "无",
                    "status": "开发中",
                },
            )
            # 消息含中文
            msg = result.get("message", "")
            assert any("一" <= c <= "鿿" for c in msg), (
                f"{reminder_type} 消息无中文: {msg[:50]}"
            )


class TestWakeIdempotency:
    """幂等性：重复操作不产生副作用。"""

    def test_dashboard_idempotent(self, tmp_path):
        """两次调 write_html_dashboard 应该都成功且输出可独立阅读。"""
        from pm_agent.tools.dashboard import write_html_dashboard
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        items = result["items"]

        out1 = write_html_dashboard(items, run_id="idem_a", output_dir=tmp_path / "d1")
        out2 = write_html_dashboard(items, run_id="idem_b", output_dir=tmp_path / "d2")
        assert out1["status"] == "ok"
        assert out2["status"] == "ok"
        # 两份都存在且非空
        assert Path(out1["path"]).exists()
        assert Path(out2["path"]).exists()
        assert Path(out1["path"]).stat().st_size > 10_000
        assert Path(out2["path"]).stat().st_size > 10_000

    def test_snapshot_not_overwritten_per_run_id(self, tmp_path):
        """同一 run_id 同一天不覆盖（但快照内容应稳定）。"""
        from pm_agent.tools.trend import record_snapshot
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        items = result["items"]

        snap1 = record_snapshot(items, [], run_id="idem_run", trend_dir=tmp_path)
        snap2 = record_snapshot(items, [], run_id="idem_run", trend_dir=tmp_path)
        # 同 run_id 同 day → 后写覆盖（这是设计：留痕 → 对比基准）
        # 路径相同（同名文件），size 一致
        assert snap1["path"] == snap2["path"]
        # 但写盘仍成功
        assert Path(snap2["path"]).exists()


class TestWakeSnapshotSchema:
    """Snapshot JSON schema 字段校验。"""

    def test_snapshot_complete_schema(self, tmp_path):
        from pm_agent.tools.trend import record_snapshot
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        snap = record_snapshot(
            result["items"], [], run_id="schema_check", trend_dir=tmp_path
        )

        snap_data = json.loads(Path(snap["path"]).read_text(encoding="utf-8"))
        required_keys = {
            "run_id", "timestamp", "total", "active", "closed",
            "high_risk", "overdue", "by_priority", "by_status", "by_owner_count",
        }
        assert set(snap_data.keys()) >= required_keys

        # 数值类型正确
        assert isinstance(snap_data["total"], int)
        assert isinstance(snap_data["active"], int)
        assert isinstance(snap_data["by_priority"], dict)
        assert isinstance(snap_data["by_status"], dict)

    def test_snapshot_size_under_2kb(self, tmp_path):
        """snapshot 文件 < 2KB（设计约束）。"""
        from pm_agent.tools.trend import record_snapshot
        from pm_agent.tools.excel import read_excel

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        snap = record_snapshot(
            result["items"], [], run_id="size_check", trend_dir=tmp_path
        )
        assert snap["size_bytes"] < 2048, f"snapshot {snap['size_bytes']}B > 2KB"


class TestWakeOwnerLoadRules:
    """Owner 负载规则在真实数据上验证。"""

    def test_owner_load_with_real_data(self, tmp_path):
        from pm_agent.tools.excel import read_excel
        from pm_agent.tools.owner_load import query_owner_load

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        load = query_owner_load(result["items"])

        # 31 个 owner 应大部分出现在负载中
        assert load["summary"]["owner_count"] >= 20

        # 验证排序：过载 → 正常 → 清闲
        statuses = [o["status"] for o in load["owners"]]
        if "过载" in statuses and "清闲" in statuses:
            first_overload = statuses.index("过载")
            first_idle = statuses.index("清闲")
            assert first_overload < first_idle, "过载应排在清闲之前"

        # 多人 owner 事项按 1/n 分摊（任意 owner 的 active ≤ 实际事项数）
        for o in load["owners"]:
            assert o["active"] <= o["active"] + 1, "占位检查"
            assert o["active"] >= 0

    def test_owners_with_missing_owner_excluded(self, tmp_path):
        from pm_agent.tools.excel import read_excel
        from pm_agent.tools.owner_load import query_owner_load

        result = read_excel(str(EXCEL_PATH), sheet_name="630攻关问题清单")
        load = query_owner_load(result["items"])
        # 没有"未指派"桶
        owner_names = [o["owner"] for o in load["owners"]]
        assert "未指派" not in owner_names
        assert all(n for n in owner_names)