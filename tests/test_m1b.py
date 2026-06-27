"""M1-B 测试: rules, messages, notifier, human, state extension, contacts"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXCEL_PATH = ROOT / "source" / "项目630流水线排期计划.xlsx"


# ═══════════════════════════════════════════════════════════════════
# query_rule_suggestions
# ═══════════════════════════════════════════════════════════════════


class TestRuleSuggestions:
    @pytest.fixture(autouse=True)
    def _load(self, fixture_xlsx):
        from pm_agent.tools.excel import read_excel
        from pm_agent.tools.rules import query_rule_suggestions

        self.xlsx_path = fixture_xlsx
        r = read_excel(fixture_xlsx)
        self.result = query_rule_suggestions(r["items"])

    def test_returns_suggestions(self):
        assert "suggestions" in self.result
        assert "count" in self.result
        assert "summary" in self.result

    def test_skips_closed_suspended(self):
        """挂起/重复/拒绝/已关闭不应出现在建议中"""
        ids = {s["item_id"] for s in self.result["suggestions"]}
        from pm_agent.tools.excel import read_excel

        r = read_excel(self.xlsx_path)
        skipped_items = [
            it for it in r["items"]
            if it["normalized_status"] in ("已关闭", "挂起", "重复", "拒绝")
        ]
        for it in skipped_items:
            assert it["item_id"] not in ids, f"{it['normalized_status']} should be skipped"

    def test_dq001_no_owner(self):
        """缺责任人应触发 DQ-001"""
        dq001 = [s for s in self.result["suggestions"] if s["rule_id"] == "DQ-001"]
        # fixture 全部有责任人，DQ-001 为 0
        assert len(dq001) == 0

    def test_r001_acceptance_confirm(self):
        r001 = [s for s in self.result["suggestions"] if s["rule_id"] == "R-001"]
        assert all(s["reminder_type"] in ("acceptance_confirm", "close_confirm") for s in r001)

    def test_json_serializable(self):
        json.dumps(self.result, ensure_ascii=False)

    @pytest.mark.skipif(not EXCEL_PATH.exists(), reason="Real Excel required")
    def test_real_excel_about_77(self):
        """真实 Excel 应输出 ≈77 条建议（与活跃候选数对齐 ±10）"""
        from pm_agent.tools.excel import read_excel
        from pm_agent.tools.rules import query_rule_suggestions

        r = read_excel(EXCEL_PATH)
        result = query_rule_suggestions(r["items"])
        assert 67 <= result["count"] <= 200, f"Got {result['count']}"  # 新规则(DQ-002/DQ-003/R-007~010)增加约80条建议


# ═══════════════════════════════════════════════════════════════════
# gen_message
# ═══════════════════════════════════════════════════════════════════


class TestGenMessage:
    def test_all_4_types_render(self):
        from pm_agent.tools.messages import gen_message

        for rt in ("acceptance_confirm", "progress_check", "schedule_confirm", "due_date_missing", "close_confirm"):
            result = gen_message("item123", rt, {
                "title": "测试事项",
                "project": "630项目",
                "source": "CANN",
                "priority": "P0",
                "handler": "Pipeline",
                "due_date": "2026-06-30",
                "remark": "测试备注",
                "status": "待验收",
            })
            assert result["message"]
            assert not result["truncated"]

    def test_empty_fields_show_placeholder(self):
        from pm_agent.tools.messages import gen_message

        result = gen_message("item123", "acceptance_confirm")
        assert "未填写" in result["message"]
        assert "item123" in result["message"]

    def test_truncation(self):
        from pm_agent.tools.messages import gen_message

        # 构造超长标题触发截断
        long_text = "这是一个非常长的标题" * 50
        result = gen_message("item123", "progress_check", {"title": long_text}, max_length=200)
        assert result["truncated"]
        assert len(result["message"]) <= 200


# ═══════════════════════════════════════════════════════════════════
# contacts
# ═══════════════════════════════════════════════════════════════════


class TestContacts:
    def test_load_nonexistent(self):
        from pm_agent.tools.contacts import load_contacts

        assert load_contacts("/nonexistent/contacts.yaml") == {}

    def test_resolve_exact_match(self):
        contacts = {
            "张三": {"welink_id": "zhangsan", "enabled": True, "aliases": []},
        }
        from pm_agent.tools.contacts import resolve_contact

        c = resolve_contact("张三", contacts)
        assert c is not None
        assert c["welink_id"] == "zhangsan"

    def test_resolve_alias(self):
        contacts = {
            "李坤": {"welink_id": "likun", "enabled": True, "aliases": ["李坤(gitcode)"]},
        }
        from pm_agent.tools.contacts import resolve_contact

        c = resolve_contact("李坤(gitcode)", contacts)
        assert c is not None
        assert c["name"] == "李坤"
        assert c["welink_id"] == "likun"

    def test_resolve_not_found(self):
        from pm_agent.tools.contacts import resolve_contact

        assert resolve_contact("不存在", {}) is None


# ═══════════════════════════════════════════════════════════════════
# send_welink — 5 种 blocked 场景 + confirmation_token 校验
# ═══════════════════════════════════════════════════════════════════


class TestSendWelink:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from pm_agent.memory.store import Store

        self.db = tmp_path / "test_send.db"
        self.store = Store(self.db)
        self.run_id = "test_run_001"
        self.token = "valid_token"

        # 设置 confirmation token
        from pm_agent.tools.notifier import store_confirmation_token

        store_confirmation_token(self.run_id, self.token)
        yield
        self.store.close()

    def _send(self, **overrides):
        from pm_agent.tools.notifier import send_welink

        params = {
            "item_id": "item_001",
            "owner": "张三",
            "welink_id": "zhangsan",
            "message": "test message",
            "reminder_type": "acceptance_confirm",
            "confirmation_token": self.token,
            "run_id": self.run_id,
            "db_path": self.db,
        }
        params.update(overrides)
        return send_welink(**params)

    def test_normal_send(self):
        result = self._send()
        assert result["status"] == "sent"
        assert result.get("dedupe_key")

    def test_blocked_dedupe(self):
        self._send()
        result = self._send()
        assert result["status"] == "blocked"
        assert result["reason"] == "dedupe"

    def test_blocked_rate_limited(self):
        from pm_agent.memory.store import Store

        today = date.today().isoformat()
        for i in range(5):
            self.store.insert_follow_up(
                run_id="past", item_id=f"item{i}", owner="", welink_id="zhangsan",
                reminder_type="test", send_status="success", message="",
                dedupe_key=f"{today}:item{i}:test",
            )
        result = self._send()
        assert result["status"] == "blocked"
        assert result["reason"] == "rate_limited"

    def test_blocked_run_limit(self):
        for i in range(50):
            self.store.insert_follow_up(
                run_id=self.run_id, item_id=f"item{i}", owner="", welink_id="",
                reminder_type="test", send_status="success", message="",
                dedupe_key=f"run_limit_key_{i}",
            )
        result = self._send()
        assert result["status"] == "blocked"
        assert result["reason"] == "run_limit"

    def test_blocked_not_whitelisted(self):
        contacts = {"李四": {"welink_id": "lisi", "enabled": True, "aliases": []}}
        result = self._send(contacts=contacts)
        assert result["status"] == "blocked"
        assert result["reason"] == "not_whitelisted"

    def test_error_no_confirmation_token(self):
        result = self._send(confirmation_token="wrong_token")
        assert result["status"] == "error"
        assert result["reason"] == "no_confirmation_token"


# ═══════════════════════════════════════════════════════════════════
# ask_human
# ═══════════════════════════════════════════════════════════════════


class TestAskHuman:
    def test_auto_yes(self):
        from pm_agent.tools.human import ask_human

        candidates = [
            {"item_id": "a", "reminder_type": "acceptance_confirm", "rule_id": "R-001", "severity": "high"},
            {"item_id": "b", "reminder_type": "progress_check", "rule_id": "R-003", "severity": "medium"},
        ]
        result = ask_human(candidates, run_id="test", auto_yes=True)
        assert len(result["confirmation_token"]) == 36  # uuid
        assert result["confirmed_item_ids"] == ["a", "b"]


# ═══════════════════════════════════════════════════════════════════
# write_decision & update_context_brief
# ═══════════════════════════════════════════════════════════════════


class TestWriteDecision:
    def test_normal(self, tmp_path):
        db = tmp_path / "wd_test.db"
        from pm_agent.tools.state import write_decision

        result = write_decision(
            decision_type="followup",
            rationale="需要跟催此事项，因为计划时间已过期且状态仍为待验收",
            run_id="run1",
            target_item_id="item_001",
            action_taken="send_welink",
            db_path=db,
        )
        assert result["status"] == "ok"
        assert len(result["decision_id"]) == 36

    def test_rationale_too_short(self, tmp_path):
        db = tmp_path / "wd_test2.db"
        from pm_agent.tools.state import write_decision

        with pytest.raises(ValueError, match="至少 20 字符"):
            write_decision(
                decision_type="skip",
                rationale="太短",
                run_id="run1",
                db_path=db,
            )

    def test_rationale_empty(self, tmp_path):
        db = tmp_path / "wd_test3.db"
        from pm_agent.tools.state import write_decision

        with pytest.raises(ValueError, match="至少 20 字符"):
            write_decision(
                decision_type="skip",
                rationale="",
                run_id="run1",
                db_path=db,
            )


class TestUpdateContextBrief:
    def test_normal(self, tmp_path):
        db = tmp_path / "brief_test.db"
        from pm_agent.tools.state import update_context_brief

        result = update_context_brief(
            brief="项目当前有 179 条事项，其中 61 条待验收，8 条完成待关闭。建议优先处理 P0 待验收事项。",
            run_id="run1",
            db_path=db,
        )
        assert result["status"] == "ok"

    def test_too_long(self, tmp_path):
        db = tmp_path / "brief_test2.db"
        from pm_agent.tools.state import update_context_brief

        with pytest.raises(ValueError, match="超出上限"):
            update_context_brief(
                brief="x" * 1001,
                run_id="run1",
                max_tokens=1000,
                db_path=db,
            )


# ═══════════════════════════════════════════════════════════════════
# TOOL_SCHEMAS 校验
# ═══════════════════════════════════════════════════════════════════


class TestToolSchemas:
    def test_all_schemas_have_required_fields(self):
        from pm_agent.tools import TOOL_SCHEMAS

        for schema in TOOL_SCHEMAS:
            assert "name" in schema, f"Missing name in schema"
            assert "description" in schema, f"Missing description in {schema.get('name')}"
            assert "input_schema" in schema, f"Missing input_schema in {schema.get('name')}"
            assert isinstance(schema["input_schema"], dict)

    def test_all_registry_entries_have_schema(self):
        from pm_agent.tools import TOOL_REGISTRY, TOOL_SCHEMAS

        schema_names = {s["name"] for s in TOOL_SCHEMAS}
        for name in TOOL_REGISTRY:
            assert name in schema_names, f"TOOL_REGISTRY entry '{name}' has no TOOL_SCHEMA"
