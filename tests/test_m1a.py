"""pm_agent 测试"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXCEL_PATH = ROOT / "source" / "项目630流水线排期计划.xlsx"


# ═══════════════════════════════════════════════════════════════════
# domain tests
# ═══════════════════════════════════════════════════════════════════


class TestItemId:
    def test_stable_id(self):
        from pm_agent.domain.item_id import make_item_id

        id1 = make_item_id("GitCode", "测试标题")
        id2 = make_item_id("GitCode", "测试标题")
        assert id1 == id2
        assert len(id1) == 12

    def test_different_title_different_id(self):
        from pm_agent.domain.item_id import make_item_id

        assert make_item_id("GitCode", "标题A") != make_item_id("GitCode", "标题B")

    def test_content_fingerprint_no_seq(self):
        from pm_agent.domain.item_id import make_item_id

        assert make_item_id("CANN", "同一个问题描述") == make_item_id("CANN", "同一个问题描述")

    def test_normalize_unicode(self):
        from pm_agent.domain.item_id import normalize

        assert normalize("１２３") == "123"
        assert normalize("  hello   world  ") == "hello world"
        assert normalize("Ａ，Ｂ、Ｃ") == "A,B,C"


class TestStatusMapper:
    KNOWN_COMBOS = [
        ("Open", "待验收"),
        ("Close", "已完成"),
        ("Open", "挂起(630后分析)"),
        ("Open", "待排期"),
        ("Open", "已完成"),
        ("Open", "开发中"),
        ("Close", "待验收"),
        ("Open", "重复单"),
        ("Open", "拒绝"),
        ("Close", "拒绝"),  # P3#15
    ]

    def test_all_10_combos_not_unknown(self):
        from pm_agent.domain.status_mapper import map_status

        for issue_s, support_s in self.KNOWN_COMBOS:
            result = map_status(issue_s, support_s)
            assert result != "未知", f"({issue_s}, {support_s}) → 未知"

    def test_close_reject_maps_to_reject(self):
        from pm_agent.domain.status_mapper import map_status

        assert map_status("Close", "拒绝") == "拒绝"

    def test_unknown_combo(self):
        from pm_agent.domain.status_mapper import map_status

        assert map_status("Open", "不存在的状态") == "未知"

    def test_priority_mapping(self):
        from pm_agent.domain.status_mapper import map_priority

        assert map_priority("必备(630前)") == "P0"
        assert map_priority("增强(争取630)") == "P1"
        assert map_priority("长期演进(630后)") == "P2"
        assert map_priority("拒绝(不处理)") == "Ignore"

    def test_priority_unknown_fallback_p2(self):
        from pm_agent.domain.status_mapper import map_priority

        assert map_priority("") == "P2"
        assert map_priority("garbage") == "P2"


# ═══════════════════════════════════════════════════════════════════
# excel tool — fixture-based (CI-safe, P2#2 + P2#3)
# ═══════════════════════════════════════════════════════════════════


class TestReadExcelFixture:
    @pytest.fixture(autouse=True)
    def _load(self, fixture_xlsx):
        from pm_agent.tools.excel import read_excel

        self.result = read_excel(fixture_xlsx)
        self.xlsx_path = fixture_xlsx

    def test_exact_row_count(self):
        """fixture 文件固定 11 行，断言等值而非范围（P2#3）"""
        assert self.result["count"] == 11

    def test_mtime_unchanged(self):
        from pm_agent.tools.excel import read_excel

        mtime_before = self.xlsx_path.stat().st_mtime
        read_excel(self.xlsx_path)
        mtime_after = self.xlsx_path.stat().st_mtime
        assert mtime_before == mtime_after

    def test_idempotent_ids(self):
        from pm_agent.tools.excel import read_excel

        r1 = read_excel(self.xlsx_path)
        r2 = read_excel(self.xlsx_path)
        assert [it["item_id"] for it in r1["items"]] == [it["item_id"] for it in r2["items"]]

    def test_multi_owner_parsed(self):
        multi = [it for it in self.result["items"] if len(it["owner_list"]) >= 2]
        assert len(multi) == 1
        assert set(multi[0]["owner_list"]) == {"张三", "李四"}

    def test_all_known_statuses_no_unknown(self):
        from pm_agent.domain.status_mapper import _STATUS_MAP

        for it in self.result["items"]:
            key = (it["raw_issue_status"], it["support_status"])
            if key in _STATUS_MAP:
                assert it["normalized_status"] != "未知", f"{key} → 未知"

    def test_items_json_serializable(self):
        json.dumps(self.result, ensure_ascii=False)

    def test_handler_chain_parsed(self):
        item = [it for it in self.result["items"] if it["raw_no"] == "3"][0]
        assert item["handler_chain"] == ["Pipeline", "GitCode"]

    def test_due_date_parsed(self):
        """真实 Excel 才有的 datetime 列，fixture 无此列，测试 None 路径"""
        none_dates = [it for it in self.result["items"] if it["due_date"] is None]
        assert len(none_dates) == 11  # fixture 无计划时间


# ═══════════════════════════════════════════════════════════════════
# excel tool — 真实 Excel（仅当文件存在时跑）
# ═══════════════════════════════════════════════════════════════════


class TestReadExcelReal:
    @pytest.fixture(autouse=True)
    def _load(self):
        if not EXCEL_PATH.exists():
            pytest.skip("Real Excel not found")
        from pm_agent.tools.excel import read_excel

        self.result = read_excel(EXCEL_PATH)

    def test_count_about_179(self):
        """真实 Excel 行数校验（允许 ±5 因表是活的）"""
        assert 174 <= self.result["count"] <= 184, f"Got {self.result['count']}"

    def test_multi_owner_real_count(self):
        multi = [it for it in self.result["items"] if len(it["owner_list"]) >= 2]
        assert len(multi) == 32, f"Got {len(multi)} multi-owner rows"


# ═══════════════════════════════════════════════════════════════════
# store tests
# ═══════════════════════════════════════════════════════════════════


class TestStore:
    @pytest.fixture(autouse=True)
    def _store(self, tmp_path):
        from pm_agent.memory.store import Store

        self.db = tmp_path / "test.db"
        self.store = Store(self.db)
        yield
        self.store.close()

    def test_tables_created(self):
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
        assert cur.fetchone()[0].lower() == "wal"

    def test_upsert_and_query(self):
        self.store.upsert_item_seen("abc123")
        state = self.store.get_item_state("abc123")
        assert state is not None
        assert state["reminder_count"] == 0

    def test_vanished_mark(self):
        self.store.upsert_item_seen("abc123")
        self.store.mark_vanished("abc123")
        vanished = self.store.list_vanished()
        assert len(vanished) == 1
        assert vanished[0]["item_id"] == "abc123"

    def test_vanished_rebirth(self):
        """消失 → 重现：vanished_at 应被清空（P2#6）"""
        self.store.upsert_item_seen("abc123")
        self.store.mark_vanished("abc123")
        self.store.upsert_item_seen("abc123")
        state = self.store.get_item_state("abc123")
        assert state is not None
        assert state["vanished_at"] is None
        assert self.store.list_vanished() == []

    def test_follow_up_log(self):
        rid = self.store.insert_follow_up(
            run_id="run1", item_id="abc", owner="张三",
            welink_id="zhangsan", reminder_type="acceptance_confirm",
            send_status="success", message="test msg",
            dedupe_key="2026-06-27:abc:acceptance_confirm",
        )
        assert rid > 0
        assert self.store.count_by_owner_today("zhangsan") == 1

    def test_dedupe_success_blocks(self):
        key = "2026-06-27:abc:acceptance_confirm"
        assert not self.store.exists_dedupe(key)
        self.store.insert_follow_up(
            run_id="run1", item_id="abc", owner="", welink_id="",
            reminder_type="acceptance_confirm", send_status="success",
            message="", dedupe_key=key,
        )
        assert self.store.exists_dedupe(key)

    def test_dedupe_failed_allows_retry(self):
        """failed/skipped 不应阻塞重试（P2#7）"""
        key = "2026-06-27:abc:progress_check"
        self.store.insert_follow_up(
            run_id="run1", item_id="abc", owner="", welink_id="",
            reminder_type="progress_check", send_status="failed",
            message="", dedupe_key=key,
        )
        assert not self.store.exists_dedupe(key)

    def test_dedupe_skipped_allows_retry(self):
        key = "2026-06-27:abc:schedule_confirm"
        self.store.insert_follow_up(
            run_id="run1", item_id="abc", owner="", welink_id="",
            reminder_type="schedule_confirm", send_status="skipped",
            message="", dedupe_key=key,
        )
        assert not self.store.exists_dedupe(key)

    def test_decision_log_roundtrip(self):
        """insert_decision → 可查回（P2#4）"""
        decision_id = "d-001"
        self.store.insert_decision(
            decision_id=decision_id, run_id="run1",
            decision_type="followup", rationale="测试理由",
            target_item_id="item-1", action_taken="send_welink",
        )
        cur = self.store._conn.execute(
            "SELECT id, run_id, decision_type, target_item_id, rationale, action_taken "
            "FROM decision_log WHERE id=?",
            (decision_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == decision_id
        assert row[2] == "followup"
        assert row[4] == "测试理由"

    def test_context_brief_roundtrip(self):
        """insert_brief → get_latest_brief 闭环（P2#4）"""
        self.store.insert_brief("run1", "项目摘要测试", 42)
        brief = self.store.get_latest_brief()
        assert brief is not None
        assert brief["brief"] == "项目摘要测试"
        assert brief["token_count"] == 42

    def test_list_all_item_states(self):
        self.store.upsert_item_seen("a")
        self.store.upsert_item_seen("b")
        states = self.store.list_all_item_states()
        assert len(states) == 2
        ids = {s["item_id"] for s in states}
        assert ids == {"a", "b"}


# ═══════════════════════════════════════════════════════════════════
# safety function tests  (P2#8: 边界值)
# ═══════════════════════════════════════════════════════════════════


class TestSafety:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from pm_agent.memory.store import Store

        self.db = tmp_path / "safety_test.db"
        store = Store(self.db)
        store.close()

    # dedupe_key ────────────────────────────

    def test_dedupe_key_format(self):
        from pm_agent.tools.safety import dedupe_key

        assert dedupe_key("item123", "acceptance_confirm", "2026-06-27") == \
            "2026-06-27:item123:acceptance_confirm"

    def test_dedupe_key_default_date(self):
        from pm_agent.tools.safety import dedupe_key

        assert date.today().isoformat() in dedupe_key("item123", "progress_check")

    # check_rate_limit ──────────────────────

    def _insert_n(self, welink_id: str, n: int):
        from pm_agent.memory.store import Store

        store = Store(self.db)
        today = date.today().isoformat()
        for i in range(n):
            store.insert_follow_up(
                run_id="run1", item_id=f"item{i}", owner="",
                welink_id=welink_id, reminder_type="test",
                send_status="success", message="",
                dedupe_key=f"{today}:item{i}:test",
            )
        store.close()

    def test_rate_limit_under(self):
        from pm_agent.tools.safety import check_rate_limit

        result = check_rate_limit("user1", max_per_day=5, db_path=self.db)
        assert result["allowed"] is True
        assert result["current"] == 0

    def test_rate_limit_n_minus_1_allowed(self):
        """max-1 时仍允许（P2#8）"""
        self._insert_n("user_lim", 4)
        from pm_agent.tools.safety import check_rate_limit

        result = check_rate_limit("user_lim", max_per_day=5, db_path=self.db)
        assert result["allowed"] is True
        assert result["current"] == 4

    def test_rate_limit_at_max_denied(self):
        """恰好等于 max 时拒绝（P2#8）"""
        self._insert_n("user_max", 5)
        from pm_agent.tools.safety import check_rate_limit

        result = check_rate_limit("user_max", max_per_day=5, db_path=self.db)
        assert result["allowed"] is False
        assert result["current"] == 5

    def test_rate_limit_over_max_denied(self):
        """max+1 时拒绝且 current 正确（P2#8）"""
        self._insert_n("user_over", 6)
        from pm_agent.tools.safety import check_rate_limit

        result = check_rate_limit("user_over", max_per_day=5, db_path=self.db)
        assert result["allowed"] is False
        assert result["current"] == 6

    # check_run_limit ───────────────────────

    def _insert_run_n(self, run_id: str, n: int):
        from pm_agent.memory.store import Store

        store = Store(self.db)
        for i in range(n):
            store.insert_follow_up(
                run_id=run_id, item_id=f"item{i}", owner="",
                welink_id="", reminder_type="test",
                send_status="success", message="",
                dedupe_key=f"run_key_{run_id}_{i}",
            )
        store.close()

    def test_run_limit_under(self):
        from pm_agent.tools.safety import check_run_limit

        result = check_run_limit("run1", max_per_run=50, db_path=self.db)
        assert result["allowed"] is True

    def test_run_limit_n_minus_1_allowed(self):
        """max-1 时仍允许（P2#8）"""
        self._insert_run_n("run_n1", 49)
        from pm_agent.tools.safety import check_run_limit

        result = check_run_limit("run_n1", max_per_run=50, db_path=self.db)
        assert result["allowed"] is True
        assert result["current"] == 49

    def test_run_limit_at_max_denied(self):
        """恰好等于 max 时拒绝（P2#8）"""
        self._insert_run_n("run_eq50", 50)
        from pm_agent.tools.safety import check_run_limit

        result = check_run_limit("run_eq50", max_per_run=50, db_path=self.db)
        assert result["allowed"] is False
        assert result["current"] == 50

    def test_run_limit_over_max_denied(self):
        """max+1 时拒绝（P2#8）"""
        self._insert_run_n("run_over", 51)
        from pm_agent.tools.safety import check_run_limit

        result = check_run_limit("run_over", max_per_run=50, db_path=self.db)
        assert result["allowed"] is False
        assert result["current"] == 51


# ═══════════════════════════════════════════════════════════════════
# query_state integration test
# ═══════════════════════════════════════════════════════════════════


class TestQueryState:
    def test_query_empty(self, tmp_path):
        db = tmp_path / "qs_test.db"
        from pm_agent.tools.state import query_state

        assert query_state(db_path=db)["count"] == 0

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

    def test_query_all_after_insert(self, tmp_path):
        db = tmp_path / "qs_test3.db"
        from pm_agent.memory.store import Store
        from pm_agent.tools.state import query_state

        store = Store(db)
        store.upsert_item_seen("a")
        store.upsert_item_seen("b")
        store.close()

        result = query_state(db_path=db)
        assert result["count"] == 2
