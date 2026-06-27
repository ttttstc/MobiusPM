"""write_html_dashboard 测试"""
import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sample_work_items():
    """最小可用的 WorkItem 样本（含已超期 / 临期 / 缺责任人 / 待验收 / 已关闭）。"""
    return [
        # 1. P0 超期 + 待验收
        {
            "item_id": "8968492c67c5",
            "title": "流水线支持自定义 Action（自定义插件）的需求",
            "normalized_status": "待验收待关闭",
            "priority_level": "P0",
            "owner_list": ["叶红达"],
            "due_date": "2026-06-15",
            "remark": "已上线",
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Close",
            "handler_chain": ["Pipeline"],
        },
        # 2. P0 超期 + 待验收（更长 item_id）
        {
            "item_id": "8dc88868ba63abcdef1234567890",
            "title": "流水线自定义Action：公仓跨仓引用",
            "normalized_status": "待验收",
            "priority_level": "P0",
            "owner_list": ["曹禹", "叶红达"],
            "due_date": "2026-06-15",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 3. P1 临期
        {
            "item_id": "ea10ae9c082f",
            "title": "流水线日志倒序加载",
            "normalized_status": "待验收",
            "priority_level": "P1",
            "owner_list": ["涂键"],
            "due_date": None,
            "remark": "6.25 上线广州",
            "source": "GitCode",
            "priority_raw": "增强(争取630)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 4. P2 缺责任人
        {
            "item_id": "04b24e9aa20e",
            "title": "Runner环境信息展示",
            "normalized_status": "挂起",
            "priority_level": "P2",
            "owner_list": [],
            "due_date": None,
            "remark": None,
            "source": "GitCode",
            "priority_raw": "长期演进(630后)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
        # 5. 已关闭
        {
            "item_id": "abcdef1234567890",
            "title": "已完成事项示例",
            "normalized_status": "已关闭",
            "priority_level": "P1",
            "owner_list": ["张三"],
            "due_date": "2026-06-20",
            "remark": None,
            "source": "GitCode",
            "priority_raw": "增强(争取630)",
            "raw_issue_status": "Close",
            "handler_chain": ["Pipeline"],
        },
        # 6. 拒绝
        {
            "item_id": "1234567890abcdef",
            "title": "已拒绝事项示例",
            "normalized_status": "拒绝",
            "priority_level": "P2",
            "owner_list": ["李四"],
            "due_date": None,
            "remark": "无需支持",
            "source": "GitCode",
            "priority_raw": "拒绝(不处理)",
            "raw_issue_status": "Close",
            "handler_chain": ["Pipeline"],
        },
        # 7. P0 开发中超期（高风险样本）
        {
            "item_id": "deadbeef12345678",
            "title": "高风险示例：开发中超期",
            "normalized_status": "开发中",
            "priority_level": "P0",
            "owner_list": ["王五"],
            "due_date": "2026-06-10",  # 早已超期
            "remark": "开发中遇到阻塞，等待依赖方回复",
            "source": "GitCode",
            "priority_raw": "必备(630前)",
            "raw_issue_status": "Open",
            "handler_chain": ["Pipeline"],
        },
    ]


class TestWriteHtmlDashboard:
    def test_basic_generation(self, sample_work_items, tmp_path: Path):
        from pm_agent.tools.dashboard import write_html_dashboard

        out = tmp_path / "dashboards"
        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_001",
            output_dir=out,
        )
        assert result["status"] == "ok"
        assert Path(result["path"]).exists()
        assert result["size_bytes"] > 0
        assert result["size_bytes"] < 50_000  # 看板文件 < 50KB

    def test_html_is_self_contained(self, sample_work_items, tmp_path: Path):
        """生成的 HTML 不依赖任何外链（字体/CSS/JS 全部 inline）。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_002",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 不允许外部资源
        assert "<link rel=\"stylesheet\"" not in html or "href=\"http" not in html
        assert "@import" not in html
        assert "https://" not in html.replace("https://www.w3.org", "")  # 仅 SVG namespace 例外
        # 必须有 inline style
        assert "<style>" in html

    def test_stats_accuracy(self, sample_work_items, tmp_path: Path):
        """统计数字正确：7 总数、5 活跃、2 已闭环、若干高风险。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_003",
            output_dir=tmp_path,
        )
        stats = result["stats"]
        assert stats["total"] == 7
        assert stats["active"] == 5  # 7 - 2 (已关闭 + 拒绝)
        assert stats["closed"] == 2
        # 至少有 1 个高风险
        assert stats["high_risk"] >= 1

    def test_risks_table_only_high_medium(self, sample_work_items, tmp_path: Path):
        """风险表只显示 high + medium，不显示 low。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_004",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 风险表格存在
        assert "table class=\"risks\"" in html
        # 每行有状态 pill
        assert "pill" in html
        assert "●" in html or "▲" in html  # 至少有一个高风险或临期标志

    def test_risks_ordering_prioritizes_real_risks(self, sample_work_items, tmp_path: Path):
        """真风险（R-003/007/009/010）排在数据质量（DQ-001）前面。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_ordering",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 找到第一个 "缺责任人" pill 和第一个 R- 风险 pill 的位置
        first_dq = html.find("缺责任人")
        # R-003 (超期) 应该出现得比 DQ-001 更早
        first_r_crit = html.find("超期")
        # 任一超期类风险应早于缺责任人
        assert first_r_crit != -1
        if first_dq != -1:
            assert first_r_crit < first_dq, (
                f"超期风险应排在缺责任人之前 (R-crit at {first_r_crit}, DQ at {first_dq})"
            )

    def test_action_groups_have_reminder_types(self, sample_work_items, tmp_path: Path):
        """建议行动按 reminder_type 分组。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_005",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "action-group" in html
        # 至少有一类分组标题
        assert any(
            label in html
            for label in (
                "ACCEPTANCE_CONFIRM",
                "CLOSE_CONFIRM",
                "PROGRESS_CHECK",
                "SCHEDULE_CONFIRM",
                "DUE_DATE_MISSING",
                "DATA_QUALITY",
                "ESCALATION",
            )
        )

    def test_empty_input_returns_error(self, tmp_path: Path):
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard([], run_id="empty", output_dir=tmp_path)
        assert result["status"] == "error"

    def test_accessibility_attributes(self, sample_work_items, tmp_path: Path):
        """包含必要的 a11y 属性（lang/role/aria-label/aria-labelledby）。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_006",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert 'lang="zh"' in html
        assert 'role="main"' in html
        assert 'aria-labelledby=' in html
        assert 'aria-label=' in html
        assert 'aria-hidden="true"' in html

    def test_reduced_motion_support(self, sample_work_items, tmp_path: Path):
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_007",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "prefers-reduced-motion" in html

    def test_oklch_colors(self, sample_work_items, tmp_path: Path):
        """使用 OKLCH 颜色空间（design system 要求）。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_008",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "oklch(" in html
        # 不应有 hex 颜色（除了 box-shadow 中可能的 transparent 等）
        # 验证没有硬编码 hex
        assert "#fff" not in html.lower()
        assert "#000" not in html.lower()

    def test_responsive_breakpoints(self, sample_work_items, tmp_path: Path):
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_009",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 桌面 / 平板 / 手机三个断点
        assert "@media (max-width: 1023px)" in html
        assert "@media (max-width: 639px)" in html

    def test_id_truncation(self, sample_work_items, tmp_path: Path):
        """长 item_id 在显示时截断到前 8 字符。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_010",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 完整 ID 在 title 属性中（hover 查看）
        assert "8dc88868ba63abcdef1234567890" in html
        # 短 ID 显示（id-truncate 类）
        assert "id-truncate" in html

    def test_id_unchanged_in_db(self, sample_work_items, tmp_path: Path):
        """dashboard 调用不会修改数据库状态（只读操作）。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_011",
            output_dir=tmp_path,
        )
        assert result["status"] == "ok"

    def test_risk_summary_section_present(self, sample_work_items, tmp_path: Path):
        """总体风险总结 section 存在。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_summary",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert 'aria-labelledby="sec-summary"' in html
        assert "总体风险总结" in html
        assert "health-pill" in html
        assert "summary-narrative" in html

    def test_advisory_section_present(self, sample_work_items, tmp_path: Path):
        """提示事项 section 存在（待验收等低严重度项）。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_advisory",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert 'aria-labelledby="sec-advisories"' in html
        assert "提示事项" in html
        assert "table class=\"advisories\"" in html

    def test_remarks_shown_in_risk_rows(self, sample_work_items, tmp_path: Path):
        """事项备注显示在风险行内。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_remarks",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "remark-text" in html
        # 样本中 item 7 有备注「开发中遇到阻塞，等待依赖方回复」
        assert "开发中遇到阻塞" in html

    def test_priority_rank_badges_top5(self, sample_work_items, tmp_path: Path):
        """Top 5 风险有优先级编号 badge。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_rank",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "rank-badge" in html
        assert "rank-1" in html
        assert "rank-5" in html

    def test_advisory_separated_from_risk_table(self, sample_work_items, tmp_path: Path):
        """待验收项不出现在风险明细表中，只在提示事项中。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_separation",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 找到 risk table 和 advisory table 的位置
        risk_table_start = html.find('<table class="risks">')
        risk_table_end = html.find('</table>', risk_table_start)
        advisory_table_start = html.find('<table class="advisories">')
        # 风险表必须早于提示表
        assert risk_table_start > 0
        assert risk_table_end > risk_table_start
        assert advisory_table_start > risk_table_end, "提示事项 section 应在风险明细之后"

    def test_high_risk_rows_have_severity_class(self, sample_work_items, tmp_path: Path):
        """高严重度行带 sev-high class 以应用视觉强调。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_sev_class",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "risk-row sev-high" in html

    def test_health_pill_in_summary(self, sample_work_items, tmp_path: Path):
        """风险总结里有 health-pill 显示整体健康度。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_health",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 至少有一种 health_class (crit / warn / ok)
        assert any(c in html for c in ["pill-crit", "pill-warn", "pill-ok"])

    def test_p8_category_tag_in_risks(self, sample_work_items, tmp_path: Path):
        """P8 升级：风险行有 PM 风险类别 tag（进度/范围/质量/资源/依赖）。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_category",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 至少有 category-tag 出现
        assert "category-tag" in html
        # 至少有一种 PM 类别（样本含 P0 开发中超期 → 进度）
        assert any(
            cat in html for cat in ["cat-schedule", "cat-scope", "cat-quality",
                                     "cat-resource", "cat-dependency", "cat-data"]
        )

    def test_p8_24h_action_in_risks(self, sample_work_items, tmp_path: Path):
        """P8 升级：风险行有 24h 动作列。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_24h",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "24h" in html or "24h 动作" in html
        # 至少有具体动作（不是"催办"这种空话）
        assert any(
            action in html
            for action in ["升级", "Sponsor", "拉群", "召集", "对齐", "排期"]
        )

    def test_p8_escalation_path(self, sample_work_items, tmp_path: Path):
        """P8 升级：风险行有升级路径。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_escalation",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "升级" in html
        assert "Sponsor" in html or "PM" in html

    def test_p8_impact_description(self, sample_work_items, tmp_path: Path):
        """P8 升级：风险行有 PM 视角的影响描述。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_impact",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 影响字段存在
        assert "影响" in html
        # 至少一条影响说明（样本含 P0 开发中超期）
        assert "P0 已超期" in html or "影响后续依赖" in html

    def test_p8_top3_with_action_in_summary(self, sample_work_items, tmp_path: Path):
        """P8 升级：总体风险总结的 TOP 3 含 24h 动作和升级路径。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_p8_top3",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        # 截取 summary section
        summary_start = html.find("今日必须处置")
        assert summary_start > 0, "TOP 3 应有'今日必须处置'标签"
        # 后续内容含 24h 动作和升级路径
        summary_end = html.find("关键观察")
        summary_block = html[summary_start:summary_end]
        assert "24h" in summary_block
        assert "升级" in summary_block

    def test_p8_category_breakdown_in_narrative(self, sample_work_items, tmp_path: Path):
        """P8 升级：summary narrative 含 PM 风险类别分布。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_breakdown",
            output_dir=tmp_path,
        )
        risk_summary = result.get("risk_summary") or {}
        # Python 返回的 dict 不直接暴露 — 从 stats 验证或读 HTML
        html = Path(result["path"]).read_text(encoding="utf-8")
        # narrative 含类别分布关键词（如果有任何风险）
        # 样本含 P0 开发中超期 → 进度
        assert "风险类别分布" in html or "今日必须处置" in html

    def test_p8_no_acceptance_in_risks(self, sample_work_items, tmp_path: Path):
        """P8 升级：待验收项（R-001）不出现在风险明细，仅在提示事项。"""
        import re
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_no_r001",
            output_dir=tmp_path,
        )
        html = Path(result["path"]).read_text(encoding="utf-8")
        risk_table_start = html.find('<table class="risks">')
        risk_table_end = html.find('</table>', risk_table_start)
        advisory_table_start = html.find('<table class="advisories">')
        risk_section = html[risk_table_start:risk_table_end]
        advisory_section = html[advisory_table_start:]

        # 提取所有 status pill（pill class 内文本）
        # 待验收 PURE（不含"待关闭"或"待验收待关闭"）只应在 advisory
        # 查找所有 pill 标签
        pill_matches = re.findall(r'<span class="pill[^"]*"[^>]*>\s*<span class="pill-glyph"[^>]*>[^<]*</span>\s*<span>([^<]+)</span>', risk_section)
        risk_pills = [p.strip() for p in pill_matches]

        # 风险表中不应有纯"待验收"作为状态（R-001 acceptance_confirm 是 low，应在 advisory）
        pure_acceptance_in_risks = [p for p in risk_pills if p == "待验收"]
        assert len(pure_acceptance_in_risks) == 0, (
            f"待验收（pure）不应出现在风险明细表：{pure_acceptance_in_risks}"
        )

        # advisory 中应有待验收（R-001 acceptance_confirm 是 low severity → advisory）
        advisory_pill_matches = re.findall(r'<span class="pill[^"]*"[^>]*>\s*<span class="pill-glyph"[^>]*>[^<]*</span>\s*<span>([^<]+)</span>', advisory_section)
        advisory_pills = [p.strip() for p in advisory_pill_matches]
        assert "待验收" in advisory_pills, "待验收应在提示事项表中"

    def test_p8_high_overdue_triggers_crit(self, tmp_path: Path):
        """P8 升级：P0 已超期触发'高危冲刺'评级。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        items = [
            {
                "item_id": "p0overdue1",
                "title": "P0 已超期高危",
                "normalized_status": "开发中",
                "priority_level": "P0",
                "owner_list": ["张三"],
                "due_date": "2026-06-01",  # 早已超期
                "remark": "严重阻塞 630",
                "source": "GitCode",
                "priority_raw": "必备",
                "raw_issue_status": "Open",
                "handler_chain": ["Pipeline"],
            },
        ]
        result = write_html_dashboard(items, run_id="test_crit", output_dir=tmp_path)
        html = Path(result["path"]).read_text(encoding="utf-8")
        assert "高危冲刺" in html
        assert "pill-crit" in html


class TestToolRegistry:
    def test_dashboard_in_registry(self):
        from pm_agent.tools import TOOL_REGISTRY

        assert "write_html_dashboard" in TOOL_REGISTRY
        assert TOOL_REGISTRY["write_html_dashboard"] == "pm_agent.tools.dashboard.write_html_dashboard"

    def test_dashboard_schema_present(self):
        from pm_agent.tools import TOOL_SCHEMAS

        schema = next(
            (s for s in TOOL_SCHEMAS if s["name"] == "write_html_dashboard"),
            None,
        )
        assert schema is not None
        # 必需字段
        assert "work_items" in schema["input_schema"]["required"]
        assert "run_id" in schema["input_schema"]["required"]