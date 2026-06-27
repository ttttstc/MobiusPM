"""pm_agent 测试"""
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXCEL_PATH = ROOT / "source" / "项目630流水线排期计划.xlsx"


# ── domain tests ──


class TestItemId:
    def test_stable_id(self):
        from pm_agent.domain.item_id import make_item_id

        id1 = make_item_id("GitCode", "测试标题")
        id2 = make_item_id("GitCode", "测试标题")
        assert id1 == id2
        assert len(id1) == 12

    def test_different_title_different_id(self):
        from pm_agent.domain.item_id import make_item_id

        id1 = make_item_id("GitCode", "标题A")
        id2 = make_item_id("GitCode", "标题B")
        assert id1 != id2

    def test_no_seq_in_id(self):
        """itemId 不包含序号"""
        from pm_agent.domain.item_id import make_item_id

        # 两个不同序号但相同内容的行应产生相同 itemId
        id1 = make_item_id("CANN", "同一个问题描述")
        id2 = make_item_id("CANN", "同一个问题描述")
        assert id1 == id2

    def test_normalize_unicode(self):
        from pm_agent.domain.item_id import normalize

        # NFKC: 全角数字 → 半角
        assert normalize("１２３") == "123"
        # 空白压缩
        assert normalize("  hello   world  ") == "hello world"
        # 中文标点统一
        assert normalize("Ａ，Ｂ、Ｃ") == "A,B,C"


class TestStatusMapper:
    def test_all_9_combos(self):
        """9 种已知组合全部不为 '未知'"""
        from pm_agent.domain.status_mapper import map_status

        combos = [
            ("Open", "待验收"),
            ("Close", "已完成"),
            ("Open", "挂起(630后分析)"),
            ("Open", "待排期"),
            ("Open", "已完成"),
            ("Open", "开发中"),
            ("Close", "待验收"),
            ("Open", "重复单"),
            ("Open", "拒绝"),
        ]
        for issue_s, support_s in combos:
            result = map_status(issue_s, support_s)
            assert result != "未知", f"({issue_s}, {support_s}) mapped to '未知'"

    def test_unknown_combo(self):
        from pm_agent.domain.status_mapper import map_status

        assert map_status("Open", "不存在的状态") == "未知"

    def test_priority_mapping(self):
        from pm_agent.domain.status_mapper import map_priority

        assert map_priority("必备(630前)") == "P0"
        assert map_priority("增强(争取630)") == "P1"
        assert map_priority("长期演进(630后)") == "P2"
        assert map_priority("拒绝(不处理)") == "Ignore"


# ── excel tool tests ──


class TestReadExcel:
    @pytest.fixture(autouse=True)
    def _load(self):
        if not EXCEL_PATH.exists():
            pytest.skip("Excel file not found")
        from pm_agent.tools.excel import read_excel

        self.result = read_excel(EXCEL_PATH)

    def test_count_179_plus_minus_5(self):
        assert 174 <= self.result["count"] <= 184, f"Got {self.result['count']}"

    def test_mtime_unchanged(self):
        """运行前后 mtime 不变（read_excel 内部已有 assert，此为显式验证）"""
        import openpyxl

        mtime_before = EXCEL_PATH.stat().st_mtime
        from pm_agent.tools.excel import read_excel

        read_excel(EXCEL_PATH)
        mtime_after = EXCEL_PATH.stat().st_mtime
        assert mtime_before == mtime_after

    def test_idempotent_ids(self):
        """同一 Excel 跑两次，所有 itemId 完全一致"""
        from pm_agent.tools.excel import read_excel

        r1 = read_excel(EXCEL_PATH)
        r2 = read_excel(EXCEL_PATH)
        ids1 = [it["item_id"] for it in r1["items"]]
        ids2 = [it["item_id"] for it in r2["items"]]
        assert ids1 == ids2

    def test_multi_owner_count(self):
        """32 条多责任人行 owner_list 长度 >= 2"""
        multi = [
            it for it in self.result["items"] if len(it["owner_list"]) >= 2
        ]
        assert len(multi) == 32, f"Got {len(multi)} multi-owner rows"

    def test_status_mapping_no_unknown(self):
        """9 种已知状态组合全部不为 '未知'"""
        statuses = {it["normalized_status"] for it in self.result["items"]}
        # 从真实数据看，应该没有未知
        unknown_items = [
            it for it in self.result["items"] if it["normalized_status"] == "未知"
        ]
        # 允许有极少量（如果出现新的组合），但 9 种已知的不能是未知
        for it in self.result["items"]:
            combo = (it["raw_issue_status"], it["support_status"])
            if combo in [
                ("Open", "待验收"),
                ("Close", "已完成"),
                ("Open", "挂起(630后分析)"),
                ("Open", "待排期"),
                ("Open", "已完成"),
                ("Open", "开发中"),
                ("Close", "待验收"),
                ("Open", "重复单"),
                ("Open", "拒绝"),
            ]:
                assert it["normalized_status"] != "未知"

    def test_items_json_serializable(self):
        """返回值可 JSON 序列化"""
        json.dumps(self.result, ensure_ascii=False)

    def test_no_seq_in_item_id(self):
        """itemId 不依赖序号——相同来源+原文产生相同 ID，无论序号多少"""
        from pm_agent.domain.item_id import make_item_id

        # 两个不同序号、相同来源+原文，应产生相同 itemId
        id_a = make_item_id("CANN", "同一个问题标题")
        id_b = make_item_id("CANN", "同一个问题标题")
        assert id_a == id_b
        # 长度 12
        assert len(id_a) == 12


# ── store tests ──


class TestStore:
    @pytest.fixture(autouse=True)
    def _store(self, tmp_path):
        from pm_agent.memory.store import Store

        self.db = tmp_path / "test.db"
        self.store = Store(self.db)
        yield
        self.store.close()

    def test_tables_created(self):
        """首次运行自动创建 4 张表"""
        cur = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {r[0] for r in cur.fetchall()}
        assert "item_state" in tables
        assert "follow_up_log" in tables
        assert "decision_log" in tables
        assert "context_brief" in tables

    def test_wal_mode(self):
        cur = self.store._conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode.lower() == "wal"

    def test_upsert_and_query(self):
        self.store.upsert_item_seen("abc123")
        state = self.store.get_item_state("abc123")
        assert state is not None
        assert state["item_id"] == "abc123"
        assert state["reminder_count"] == 0

    def test_vanished(self):
        self.store.upsert_item_seen("abc123")
        self.store.mark_vanished("abc123")
        vanished = self.store.list_vanished()
        assert len(vanished) == 1
        assert vanished[0]["item_id"] == "abc123"

    def test_follow_up_log(self):
        rid = self.store.insert_follow_up(
            run_id="run1",
            item_id="abc",
            owner="张三",
            welink_id="zhangsan",
            reminder_type="acceptance_confirm",
            send_status="success",
            message="test msg",
            dedupe_key="2026-06-27:abc:acceptance_confirm",
        )
        assert rid > 0
        assert self.store.count_by_owner_today("zhangsan") == 1

    def test_dedupe_check(self):
        key = "2026-06-27:abc:acceptance_confirm"
        assert not self.store.exists_dedupe(key)
        self.store.insert_follow_up(
            run_id="run1", item_id="abc", owner="", welink_id="",
            reminder_type="acceptance_confirm", send_status="success",
            message="", dedupe_key=key,
        )
        assert self.store.exists_dedupe(key)


# ── safety function tests ──


class TestSafety:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from pm_agent.memory.store import Store

        self.db = tmp_path / "safety_test.db"
        store = Store(self.db)
        store.close()

    def test_dedupe_key_format(self):
        from pm_agent.tools.safety import dedupe_key

        key = dedupe_key("item123", "acceptance_confirm", "2026-06-27")
        assert key == "2026-06-27:item123:acceptance_confirm"

    def test_dedupe_key_default_date(self):
        from pm_agent.tools.safety import dedupe_key

        key = dedupe_key("item123", "progress_check")
        assert date.today().isoformat() in key

    def test_rate_limit_within(self):
        from pm_agent.tools.safety import check_rate_limit

        result = check_rate_limit("user1", max_per_day=5, db_path=self.db)
        assert result["allowed"] is True
        assert result["current"] == 0
        assert result["limit"] == 5

    def test_rate_limit_exceeded(self):
        from pm_agent.memory.store import Store
        from pm_agent.tools.safety import check_rate_limit

        store = Store(self.db)
        today = date.today().isoformat()
        for i in range(5):
            store.insert_follow_up(
                run_id="run1", item_id=f"item{i}", owner="",
                welink_id="user1", reminder_type="test",
                send_status="success", message="",
                dedupe_key=f"{today}:item{i}:test",
            )
        store.close()
        result = check_rate_limit("user1", today=today, max_per_day=5, db_path=self.db)
        assert result["allowed"] is False
        assert result["current"] == 5

    def test_run_limit_within(self):
        from pm_agent.tools.safety import check_run_limit

        result = check_run_limit("run1", max_per_run=50, db_path=self.db)
        assert result["allowed"] is True

    def test_run_limit_exceeded(self):
        from pm_agent.memory.store import Store
        from pm_agent.tools.safety import check_run_limit

        store = Store(self.db)
        for i in range(50):
            store.insert_follow_up(
                run_id="run1", item_id=f"item{i}", owner="",
                welink_id="", reminder_type="test",
                send_status="success", message="",
                dedupe_key=f"key{i}",
            )
        store.close()
        result = check_run_limit("run1", max_per_run=50, db_path=self.db)
        assert result["allowed"] is False
        assert result["current"] == 50


# ── query_state integration test ──


class TestQueryState:
    def test_query_empty(self, tmp_path):
        db = tmp_path / "qs_test.db"
        from pm_agent.tools.state import query_state

        result = query_state(db_path=db)
        assert result["count"] == 0

    def test_query_after_insert(self, tmp_path):
        db = tmp_path / "qs_test2.db"
        from pm_agent.memory.store import Store
        from pm_agent.tools.state import query_state

        store = Store(db)
        store.upsert_item_seen("test_item")
        store.close()

        result = query_state(item_id="test_item", db_path=db)
        assert result["found"] is True
        assert result["state"]["item_id"] == "test_item"
