"""trend / owner_load / sponsor_brief 测试（M6 三个 feature）"""
import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_work_items_for_m6():
    """覆盖趋势 / 负载 / Sponsor brief 三个 feature 所需的 WorkItem 样本。"""
    return [
        # 1. P0 超期（高风险）
        {
            "item_id": "m6_a0000001",
            "title": "P0 开发中超期",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["张三"],
            "due_date": "2026-06-10",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 2. P1 临期
        {
            "item_id": "m6_a0000002",
            "title": "P1 临期",
            "normalized_status": "开发中",
            "priority_level": "P1",
            "owner_list": ["张三"],
            "due_date": "2026-06-30",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "增强(争取630)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 3. P0 双 owner（分摊测试）
        {
            "item_id": "m6_a0000003",
            "title": "P0 多人合作",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["张三", "李四"],
            "due_date": "2026-07-15",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 4. 李四 的 P0
        {
            "item_id": "m6_a0000004",
            "title": "李四的 P0",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["李四"],
            "due_date": "2026-06-25",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 5. 李四 的 P0
        {
            "item_id": "m6_a0000005",
            "title": "李四的另一 P0",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["李四"],
            "due_date": "2026-06-26",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 6. 王五 的 P0（瓶颈候选）
        {
            "item_id": "m6_a0000006",
            "title": "王五 P0 之一",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["王五"],
            "due_date": "2026-06-22",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        {
            "item_id": "m6_a0000007",
            "title": "王五 P0 之二",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["王五"],
            "due_date": "2026-06-23",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        {
            "item_id": "m6_a0000008",
            "title": "王五 P0 之三",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["王五"],
            "due_date": "2026-06-24",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        {
            "item_id": "m6_a0000009",
            "title": "王五 P0 之四（瓶颈触发）",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["王五"],
            "due_date": "2026-06-25",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 10. 缺责任人不计入 owner 负载
        {
            "item_id": "m6_a0000010",
            "title": "缺责任人",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": [],
            "due_date": "2026-06-30",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 11. 已关闭
        {
            "item_id": "m6_a0000011",
            "title": "已关闭",
            "normalized_status": "已关闭",
            "priority_level": "P1",
            "owner_list": ["张三"],
            "due_date": "2026-06-15",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "增强(争取630)",
            "raw_issue_status": "Close",
            "handler_chain": ["Pipeline"],
        },
    ]


# ─────────────────── Trend Feature ───────────────────


class TestTrendRecordSnapshot:
    def test_snapshot_under_2kb(self, sample_work_items_for_m6, tmp_path):
        """snapshot 文件 < 2KB。"""
        from pm_agent.tools.trend import record_snapshot

        result = record_snapshot(
            sample_work_items_for_m6,
            suggestions=[],
            run_id="m6_test_001",
            trend_dir=tmp_path,
        )
        assert result["status"] == "ok"
        assert result["size_bytes"] < 2048, f"snapshot {result['size_bytes']}B > 2KB"

    def test_snapshot_schema_complete(self, sample_work_items_for_m6, tmp_path):
        """snapshot 字段完整（含 by_priority / by_status / by_owner_count）。"""
        from pm_agent.tools.trend import record_snapshot

        suggestions = [
            {"item_id": "m6_a0000001", "rule_id": "R-003", "severity": "high"},
        ]
        result = record_snapshot(
            sample_work_items_for_m6,
            suggestions=suggestions,
            run_id="m6_schema",
            trend_dir=tmp_path,
        )
        snap = result["snapshot"]
        for k in ("run_id", "timestamp", "total", "active", "closed",
                  "high_risk", "overdue", "by_priority", "by_status", "by_owner_count"):
            assert k in snap, f"missing {k}"

    def test_snapshot_not_overwritten(self, sample_work_items_for_m6, tmp_path):
        """snapshot 文件只能写不能改（每次 run_id 唯一）。"""
        from pm_agent.tools.trend import record_snapshot

        # 不同 run_id 写入 → 应该产生 2 个文件
        record_snapshot(sample_work_items_for_m6, suggestions=[], run_id="run_a", trend_dir=tmp_path)
        record_snapshot(sample_work_items_for_m6, suggestions=[], run_id="run_b", trend_dir=tmp_path)

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 2, f"应保留 2 个 snapshot，实际 {len(files)}"


class TestTrendQueryTrend:
    def test_first_run_no_snapshot(self, tmp_path):
        """无 snapshot 时 verdict.direction='首次运行'，无 diff。"""
        from pm_agent.tools.trend import query_trend

        result = query_trend(run_id="never_called", trend_dir=tmp_path)
        assert result["status"] == "ok"
        assert result["snapshot"] is None
        assert result["verdict"]["direction"] == "首次运行"

    def test_first_run_no_diff(self, sample_work_items_for_m6, tmp_path):
        """首次写 snapshot 后查询：verdict.direction='首次对比'。"""
        from pm_agent.tools.trend import record_snapshot, query_trend

        record_snapshot(sample_work_items_for_m6, suggestions=[], run_id="first", trend_dir=tmp_path)
        result = query_trend(run_id="first", trend_dir=tmp_path)
        assert result["status"] == "ok"
        assert result["snapshot"] is not None
        assert result["diff"] is None
        assert result["verdict"]["direction"] == "首次对比"

    def test_diff_computed_for_subsequent_run(self, sample_work_items_for_m6, tmp_path):
        """第二次运行有 diff，包含数字变化和趋势判定。"""
        from pm_agent.tools.trend import record_snapshot, query_trend

        # 第一次：高风险 0
        record_snapshot(
            sample_work_items_for_m6, suggestions=[],
            run_id="m6_first",
            trend_dir=tmp_path,
        )
        # 第二次：高风险 1
        record_snapshot(
            sample_work_items_for_m6,
            suggestions=[{"item_id": "m6_a0000001", "rule_id": "R-003", "severity": "high"}],
            run_id="m6_second",
            trend_dir=tmp_path,
        )
        result = query_trend(run_id="m6_second", trend_dir=tmp_path)
        assert result["diff"] is not None
        assert "high_risk" in result["diff"]
        assert result["diff"]["high_risk"]["current"] == 1
        assert result["diff"]["high_risk"]["previous"] == 0
        assert result["verdict"]["direction"] in ("恶化", "好转", "持平")

    def test_trend_determination_worsens_on_high_risk_increase(self, sample_work_items_for_m6, tmp_path):
        """高风险增加 >3 → 判定为恶化。"""
        from pm_agent.tools.trend import record_snapshot, query_trend

        suggestions_first = [{"item_id": f"x_{i}", "rule_id": "R-003", "severity": "high"} for i in range(2)]
        suggestions_second = [{"item_id": f"y_{i}", "rule_id": "R-003", "severity": "high"} for i in range(8)]

        record_snapshot(sample_work_items_for_m6, suggestions=suggestions_first,
                        run_id="bad_first", trend_dir=tmp_path)
        record_snapshot(sample_work_items_for_m6, suggestions=suggestions_second,
                        run_id="bad_second", trend_dir=tmp_path)

        result = query_trend(run_id="bad_second", trend_dir=tmp_path)
        assert result["verdict"]["direction"] == "恶化"

    def test_10_runs_no_overwrite(self, sample_work_items_for_m6, tmp_path):
        """10 次 wake 后 trend_dir 有 10 个文件。"""
        from pm_agent.tools.trend import record_snapshot

        for i in range(10):
            record_snapshot(
                sample_work_items_for_m6,
                suggestions=[],
                run_id=f"run_{i:03d}",
                trend_dir=tmp_path,
            )
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 10


# ─────────────────── Owner Load Feature ───────────────────


class TestOwnerLoad:
    def test_multi_owner_fractional_credit(self, sample_work_items_for_m6):
        """多人 owner 事项按 1/n 分摊。"""
        from pm_agent.tools.owner_load import query_owner_load

        result = query_owner_load(sample_work_items_for_m6)
        owners = {o["owner"]: o for o in result["owners"]}

        # item 3 是 ["张三", "李四"] → 每人 1.0 + 0.5 = 1.5 active
        # 张三：item1 + item2 + item3(0.5) + item11(closed, 不计) = 2.5
        # 李四：item3(0.5) + item4 + item5 = 2.5
        assert abs(owners["张三"]["active"] - 2.5) < 0.01, f"张三={owners['张三']['active']}"
        assert abs(owners["李四"]["active"] - 2.5) < 0.01, f"李四={owners['李四']['active']}"

    def test_missing_owner_excluded(self, sample_work_items_for_m6):
        """缺责任人不计入 owner 负载。"""
        from pm_agent.tools.owner_load import query_owner_load

        result = query_owner_load(sample_work_items_for_m6)
        owner_names = [o["owner"] for o in result["owners"]]
        assert "未指派" not in owner_names
        # 没有 owner 被记到"未指派"桶
        assert all(o["owner"] for o in result["owners"])

    def test_overload_threshold_active(self, sample_work_items_for_m6):
        """active > 8 → 过载。"""
        from pm_agent.tools.owner_load import query_owner_load

        # 构造一个 owner 拥有 10 项活跃
        items = [
            {
                "item_id": f"overload_{i}",
                "title": f"item {i}",
                "normalized_status": "开发中",
                "priority_level": "P1",
                "owner_list": ["重载人"],
                "due_date": "2026-07-01",
                "remark": None,
                "source": "GitCode",
                "priority_raw": "增强(争取630)",
                "raw_issue_status": "Open",
                "handler_chain": ["Pipeline"],
            }
            for i in range(10)
        ]
        result = query_owner_load(items)
        owner = result["owners"][0]
        assert owner["status"] == "过载", f"active={owner['active']} 应触发过载"

    def test_overload_threshold_p0(self):
        """p0 > 3 → 过载。"""
        from pm_agent.tools.owner_load import query_owner_load

        items = [
            {
                "item_id": f"p0over_{i}",
                "title": f"item {i}",
                "normalized_status": "开发中",
                "priority_level": "P0",
                "owner_list": ["p0boss"],
                "due_date": "2026-07-01",
                "remark": None,
                "source": "GitCode",
                "priority_raw": "必备(630前)",
                "raw_issue_status": "Open",
                "handler_chain": ["Pipeline"],
            }
            for i in range(4)
        ]
        result = query_owner_load(items)
        owner = result["owners"][0]
        assert owner["status"] == "过载"

    def test_idle_owner(self):
        """active < 2 → 清闲。"""
        from pm_agent.tools.owner_load import query_owner_load

        items = [
            {
                "item_id": "idle_one",
                "title": "single",
                "normalized_status": "开发中",
                "priority_level": "P1",
                "owner_list": ["idle_guy"],
                "due_date": "2026-07-01",
                "remark": None,
                "source": "GitCode",
                "priority_raw": "增强(争取630)",
                "raw_issue_status": "Open",
                "handler_chain": ["Pipeline"],
            }
        ]
        result = query_owner_load(items)
        assert result["owners"][0]["status"] == "清闲"

    def test_bottleneck_flag_when_blocking_ge_3(self, sample_work_items_for_m6):
        """阻塞 ≥3 个 P0/P1 → 标红。"""
        from pm_agent.tools.owner_load import query_owner_load

        result = query_owner_load(sample_work_items_for_m6)
        owners = {o["owner"]: o for o in result["owners"]}
        # 王五 有 4 个 P0（P0 ≥3 即触发瓶颈）
        assert owners["王五"]["is_bottleneck"] is True
        assert owners["王五"]["blocking_count"] >= 3

    def test_closed_items_excluded(self, sample_work_items_for_m6):
        """已关闭事项不计入 active。"""
        from pm_agent.tools.owner_load import query_owner_load

        result = query_owner_load(sample_work_items_for_m6)
        owners = {o["owner"]: o for o in result["owners"]}
        # 张三 的 item11 已关闭 → 不计入
        # 张三 应该是 item1 + item2 + item3(0.5) = 2.5
        assert abs(owners["张三"]["active"] - 2.5) < 0.01


# ─────────────────── Sponsor Brief Feature ───────────────────


class TestSponsorBrief:
    def test_brief_under_30_lines(self, sample_work_items_for_m6, tmp_path):
        """Brief 文件 < 30 行。"""
        from pm_agent.tools.sponsor_brief import write_sponsor_brief

        suggestions = [
            {"item_id": "m6_a0000001", "rule_id": "R-003",
             "reminder_type": "progress_check", "severity": "high",
             "rationale_hint": "超期"},
        ]
        result = write_sponsor_brief(
            sample_work_items_for_m6,
            suggestions,
            run_id="m6_brief_001",
            output_dir=tmp_path,
        )
        assert result["status"] == "ok"
        assert result["line_count"] < 30, f"Brief {result['line_count']} 行超过 30"

    def test_brief_ask_count_le_3(self, sample_work_items_for_m6, tmp_path):
        """Ask ≤3 条。"""
        from pm_agent.tools.sponsor_brief import write_sponsor_brief

        # 10 个高风险建议
        suggestions = [
            {"item_id": f"m6_a000000{i}", "rule_id": "R-003",
             "reminder_type": "progress_check", "severity": "high",
             "rationale_hint": "超期"}
            for i in range(1, 10)
        ]
        result = write_sponsor_brief(
            sample_work_items_for_m6,
            suggestions,
            run_id="ask_limit",
            output_dir=tmp_path,
        )
        text = Path(result["path"]).read_text(encoding="utf-8")
        # 数 Ask 行（以 "1. **" 开头格式）
        ask_lines = [
            line for line in text.splitlines()
            if line.strip().startswith(("1.", "2.", "3.")) and "**" in line
        ]
        assert len(ask_lines) <= 3, f"Ask 行数 {len(ask_lines)} 超过 3"

    def test_brief_ask_has_5_fields(self, sample_work_items_for_m6, tmp_path):
        """每条 Ask 含 事项/状态/动作/决策/截止 5 字段。"""
        from pm_agent.tools.sponsor_brief import write_sponsor_brief

        suggestions = [
            {"item_id": "m6_a0000001", "rule_id": "R-003",
             "reminder_type": "progress_check", "severity": "high",
             "rationale_hint": "超期"},
        ]
        result = write_sponsor_brief(
            sample_work_items_for_m6,
            suggestions,
            run_id="fields_check",
            output_dir=tmp_path,
        )
        text = Path(result["path"]).read_text(encoding="utf-8")
        # 必须含 5 字段标识（中文标签）
        assert "建议" in text  # 动作
        assert "项目经理需" in text  # 决策
        assert "截止" in text  # 截止
        assert "[" in text and "]" in text  # 状态

    def test_brief_includes_trend_diff(self, sample_work_items_for_m6, tmp_path):
        """传入 trend_snapshot / trend_previous 后，Brief 含数字变化表。"""
        from pm_agent.tools.sponsor_brief import write_sponsor_brief

        snapshot = {
            "total": 11, "active": 10, "closed": 1,
            "high_risk": 3, "overdue": 2,
            "by_priority": {}, "by_status": {}, "by_owner_count": 4,
        }
        previous = {
            "total": 11, "active": 11, "closed": 0,
            "high_risk": 1, "overdue": 0,
            "by_priority": {}, "by_status": {}, "by_owner_count": 4,
        }
        suggestions = [
            {"item_id": "m6_a0000001", "rule_id": "R-003",
             "reminder_type": "progress_check", "severity": "high",
             "rationale_hint": "超期"},
        ]
        result = write_sponsor_brief(
            sample_work_items_for_m6,
            suggestions,
            run_id="with_trend",
            trend_snapshot=snapshot,
            trend_previous=previous,
            output_dir=tmp_path,
        )
        text = Path(result["path"]).read_text(encoding="utf-8")
        assert "上周" in text
        assert "本周" in text
        assert "10" in text  # active 上周
        assert "3" in text  # high_risk 本周

    def test_brief_includes_owner_load(self, sample_work_items_for_m6, tmp_path):
        """传入 owner_load 后，Brief 含过载/瓶颈统计。"""
        from pm_agent.tools.owner_load import query_owner_load
        from pm_agent.tools.sponsor_brief import write_sponsor_brief

        owner_load = query_owner_load(sample_work_items_for_m6)
        suggestions = [
            {"item_id": "m6_a0000001", "rule_id": "R-003",
             "reminder_type": "progress_check", "severity": "high",
             "rationale_hint": "超期"},
        ]
        result = write_sponsor_brief(
            sample_work_items_for_m6,
            suggestions,
            run_id="with_load",
            owner_load=owner_load,
            output_dir=tmp_path,
        )
        text = Path(result["path"]).read_text(encoding="utf-8")
        # 王五 是瓶颈
        assert "人员负载" in text
        assert "瓶颈" in text

    def test_brief_ask_decidable_not_vague(self, sample_work_items_for_m6, tmp_path):
        """Ask 决策字段必须可决策（不能是'请关注'）。"""
        from pm_agent.tools.sponsor_brief import write_sponsor_brief

        suggestions = [
            {"item_id": "m6_a0000001", "rule_id": "R-007",
             "reminder_type": "escalation", "severity": "high",
             "rationale_hint": "无响应"},
        ]
        result = write_sponsor_brief(
            sample_work_items_for_m6,
            suggestions,
            run_id="decidable",
            output_dir=tmp_path,
        )
        text = Path(result["path"]).read_text(encoding="utf-8")
        # 不含空话
        assert "请关注" not in text
        # 必须含具体决策动词
        assert any(v in text for v in ["升级", "延期", "砍范围", "切分支",
                                         "指派", "调整", "同意", "评估"])


# ─────────────────── Dashboard 集成 ───────────────────


class TestDashboardIntegration:
    def test_dashboard_has_trend_section(self, sample_work_items_for_m6, tmp_path):
        """dashboard 含「进度趋势」section。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items_for_m6,
            run_id="trend_section",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert 'aria-labelledby="sec-trend"' in html
        assert "进度趋势" in html
        assert "trend-pill" in html

    def test_dashboard_has_owner_load_section(self, sample_work_items_for_m6, tmp_path):
        """dashboard 含「人员负载」section。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items_for_m6,
            run_id="load_section",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert 'aria-labelledby="sec-owner-load"' in html
        assert "人员负载" in html
        assert "owner-load" in html

    def test_dashboard_owner_load_shows_bottleneck(self, sample_work_items_for_m6, tmp_path):
        """dashboard 上王五的瓶颈标记可见。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items_for_m6,
            run_id="bottleneck",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "王五" in html
        assert "owner-bottleneck" in html
        assert "瓶颈" in html

    def test_dashboard_sections_ordered(self, sample_work_items_for_m6, tmp_path):
        """dashboard section 顺序：趋势 → 人员负载 → 风险明细。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items_for_m6,
            run_id="order",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        trend_pos = html.find("进度趋势")
        load_pos = html.find("人员负载")
        risks_pos = html.find("风险明细")
        assert trend_pos < load_pos < risks_pos, (
            f"section 顺序错：trend={trend_pos}, load={load_pos}, risks={risks_pos}"
        )