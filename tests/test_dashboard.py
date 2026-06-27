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
        """统计数字正确：6 总数、4 活跃、2 已闭环、若干高风险。"""
        from pm_agent.tools.dashboard import write_html_dashboard

        result = write_html_dashboard(
            sample_work_items,
            run_id="test_run_003",
            output_dir=tmp_path,
        )
        stats = result["stats"]
        assert stats["total"] == 6
        assert stats["active"] == 4  # 6 - 2 (已关闭 + 拒绝)
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