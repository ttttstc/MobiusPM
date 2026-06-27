"""M2 agent 集成测试 — agent loop、memory loader、CLI 适配器"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保项目根目录可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pm_agent.config import load_config
from pm_agent.memory.loader import load_initial_context
from pm_agent.memory.store import Store
from pm_agent.tools import TOOL_REGISTRY, TOOL_SCHEMAS


# ═══════════════════════════════════════════
# Agent loop 测试
# ═══════════════════════════════════════════


class TestAgentImport:
    def test_import_agent_module(self):
        from pm_agent import agent
        assert hasattr(agent, "run_agent")

    def test_agent_run_logger(self):
        from pm_agent.agent import AgentRunLogger
        td = tempfile.mkdtemp()
        log_path = Path(td) / "test.jsonl"
        logger = AgentRunLogger(str(log_path))
        logger.log({"event": "test", "data": "hello"})
        logger.close()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "test"
        assert "timestamp" in entry

    def test_call_tool_read_excel(self, fixture_xlsx):
        from pm_agent.agent import _call_tool

        result = _call_tool("read_excel", {"excel_path": str(fixture_xlsx), "sheet_name": "630攻关问题清单"})
        assert isinstance(result, dict)
        assert "items" in result
        assert result["count"] > 0

    def test_call_tool_unknown(self):
        from pm_agent.agent import _call_tool
        result = _call_tool("no_such_tool", {})
        assert "error" in result

    def test_brief_args(self):
        from pm_agent.agent import _brief_args
        s = _brief_args({"item_id": "abc123", "message": "a" * 100})
        assert "item_id=abc123" in s
        assert "message=" in s
        # 长消息被截断
        msg_part = s.split("message=")[1]
        assert len(msg_part) <= 40 + 3  # 37 + "..."

    def test_load_system_prompt_wake(self):
        from pm_agent.agent import _load_system_prompt
        prompt = _load_system_prompt(cron_mode=False)
        assert "MobiusPM" in prompt
        assert "CRON" not in prompt

    def test_load_system_prompt_cron(self):
        from pm_agent.agent import _load_system_prompt
        prompt = _load_system_prompt(cron_mode=True)
        assert "MobiusPM" in prompt
        assert "CRON" in prompt
        assert "ask_human" in prompt or "send_welink" in prompt


# ═══════════════════════════════════════════
# Memory loader 测试
# ═══════════════════════════════════════════


class TestMemoryLoader:
    def test_load_empty_db(self):
        td = tempfile.mkdtemp()
        db = Path(td) / "empty.db"
        ctx = load_initial_context(trigger_reason="wake", db_path=str(db))
        assert "PM 已唤醒你" in ctx
        assert len(ctx) > 0

    def test_load_with_brief(self):
        td = tempfile.mkdtemp()
        db = Path(td) / "test.db"
        store = Store(str(db))
        store.insert_brief("run_001", "测试摘要：3 条事项已处理，无异常", 20)
        store.close()

        ctx = load_initial_context(trigger_reason="wake", db_path=str(db))
        assert "测试摘要" in ctx

    def test_load_with_decisions(self):
        td = tempfile.mkdtemp()
        db = Path(td) / "test.db"
        store = Store(str(db))
        store.insert_decision(
            "d001", "run_001", "followup",
            "测试决策：因进度滞后超过3天，决定催办",
            "item_001", "send_welink",
        )
        store.close()

        ctx = load_initial_context(trigger_reason="wake", db_path=str(db))
        assert "催办" in ctx

    def test_load_with_sends(self):
        td = tempfile.mkdtemp()
        db = Path(td) / "test.db"
        store = Store(str(db))
        store.insert_follow_up(
            "run_001", "item_001", "张三", "zhangsan",
            "progress_check", "mock", "测试消息",
            "test::item_001::progress_check::2026-01-01",
        )
        store.close()

        ctx = load_initial_context(trigger_reason="wake", db_path=str(db))
        assert "item_001" in ctx


# ═══════════════════════════════════════════
# Config 测试
# ═══════════════════════════════════════════


class TestConfig:
    def test_load_default_config(self):
        cfg = load_config()
        assert "anthropic" in cfg
        assert "excel" in cfg
        assert "memory" in cfg
        assert "notifier" in cfg
        assert "reminder" in cfg

    def test_config_defaults(self):
        cfg = load_config()
        assert cfg["anthropic"]["model"] == "claude-opus-4-7"
        assert cfg["anthropic"]["max_tokens"] == 4096
        assert cfg["memory"]["db_path"] == "state/pm-agent.db"
        assert cfg["notifier"]["mode"] == "mock"
        assert cfg["reminder"]["max_per_owner_per_day"] == 5

    def test_config_env_api_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        cfg = load_config()
        assert cfg["anthropic"]["api_key"] == "test-key-123"

    def test_config_missing_file(self):
        cfg = load_config("nonexistent.yaml")
        assert "anthropic" in cfg  # defaults still filled


# ═══════════════════════════════════════════
# CLI 测试
# ═══════════════════════════════════════════


class TestCLI:
    def test_main_module_import(self):
        import pm_agent.__main__
        assert hasattr(pm_agent.__main__, "main")

    def test_debug_read_excel(self, capsys, fixture_xlsx):
        from pm_agent.__main__ import cmd_debug
        import argparse
        import pm_agent.__main__ as m

        original_load = m.load_config
        try:
            m.load_config = lambda: {
                "excel": {"path": str(fixture_xlsx), "sheet": "630攻关问题清单"},
                "memory": {"db_path": ":memory:"},
            }
            cmd_debug(argparse.Namespace(
                command="debug", tool="read_excel", item_id=None,
                max_records=10, subtool=None, welink_id=None,
                reminder_type=None, run_id=None,
            ))
        finally:
            m.load_config = original_load


# ═══════════════════════════════════════════
# TOOL_SCHEMAS 验证
# ═══════════════════════════════════════════


class TestToolSchemas:
    def test_all_registered_have_schemas(self):
        schema_names = {s["name"] for s in TOOL_SCHEMAS}
        for name in TOOL_REGISTRY:
            assert name in schema_names, f"{name} 在 TOOL_REGISTRY 中但不在 TOOL_SCHEMAS 中"

    def test_all_schemas_have_registry(self):
        schema_names = {s["name"] for s in TOOL_SCHEMAS}
        for name in schema_names:
            assert name in TOOL_REGISTRY, f"{name} 在 TOOL_SCHEMAS 中但不在 TOOL_REGISTRY 中"

    def test_schema_format(self):
        """验证每个 schema 是 Anthropic 兼容格式。"""
        for s in TOOL_SCHEMAS:
            assert "name" in s
            assert "description" in s
            assert "input_schema" in s
            assert "type" in s["input_schema"]


# ═══════════════════════════════════════════
# WeLinkCliNotifier 测试
# ═══════════════════════════════════════════


class TestWeLinkCliNotifier:
    def test_import(self):
        from pm_agent.tools.notifier import WeLinkCliNotifier
        n = WeLinkCliNotifier()
        assert n._cli == "welink"
        assert n._timeout == 30

    def test_custom_params(self):
        from pm_agent.tools.notifier import WeLinkCliNotifier
        n = WeLinkCliNotifier(cli_path="/usr/bin/welink", timeout=60, retry_count=3)
        assert n._cli == "/usr/bin/welink"
        assert n._timeout == 60
        assert n._retry == 3

    @patch("subprocess.run")
    def test_send_success(self, mock_run):
        from pm_agent.tools.notifier import WeLinkCliNotifier
        mock_run.return_value = MagicMock(returncode=0, stdout="msg_001", stderr="")
        n = WeLinkCliNotifier()
        result = n.send("testuser", "测试消息")
        assert result["success"] is True
        assert result["message_id"] == "msg_001"

    @patch("subprocess.run")
    def test_send_failure(self, mock_run):
        from pm_agent.tools.notifier import WeLinkCliNotifier
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="send error")
        n = WeLinkCliNotifier()
        result = n.send("testuser", "测试消息")
        assert result["success"] is False
        assert result["error"] == "send error"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_cli_not_found(self, mock_run):
        from pm_agent.tools.notifier import WeLinkCliNotifier
        n = WeLinkCliNotifier()
        result = n.send("testuser", "测试消息")
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("subprocess.run")
    def test_retry_on_failure(self, mock_run):
        from pm_agent.tools.notifier import WeLinkCliNotifier
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="try 1 fail"),
            MagicMock(returncode=1, stdout="", stderr="try 2 fail"),
            MagicMock(returncode=0, stdout="msg_ok", stderr=""),
        ]
        n = WeLinkCliNotifier(retry_count=2)
        result = n.send("testuser", "测试消息")
        assert result["success"] is True
        assert mock_run.call_count == 3


# ═══════════════════════════════════════════
# MockNotifier 测试
# ═══════════════════════════════════════════


class TestMockNotifier:
    def test_mock_writes_to_file(self, tmp_path):
        from pm_agent.tools.notifier import MockNotifier
        output = tmp_path / "mock.jsonl"
        n = MockNotifier(str(output))
        result = n.send("user1", "hello")
        assert result["success"] is True
        assert output.exists()
        lines = output.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1


# ═══════════════════════════════════════════
# Ask human 增强展示测试
# ═══════════════════════════════════════════


class TestAskHumanDisplay:
    def test_format_table(self):
        from pm_agent.tools.human import _format_table
        candidates = [
            {"item_id": "abc123", "reminder_type": "progress_check",
             "severity": "high", "title": "测试事项标题"},
        ]
        table = _format_table(candidates)
        assert "abc123" in table
        assert "进度检查" in table
        assert "测试事项标题" in table

    def test_auto_yes_returns_token(self):
        from pm_agent.tools.human import ask_human
        result = ask_human(
            [{"item_id": "test1", "reminder_type": "progress_check", "severity": "medium"}],
            run_id="test_auto", auto_yes=True,
        )
        assert result["confirmation_token"] != ""
        assert "test1" in result["confirmed_item_ids"]

    def test_auto_yes_all_confirmed(self):
        from pm_agent.tools.human import ask_human
        candidates = [
            {"item_id": f"id_{i}", "reminder_type": "progress_check", "severity": "low"}
            for i in range(5)
        ]
        result = ask_human(candidates, run_id="test_all", auto_yes=True)
        assert len(result["confirmed_item_ids"]) == 5
