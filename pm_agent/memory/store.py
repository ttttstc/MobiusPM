from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# 默认 DB 路径，统一导出，避免各处硬编码
DEFAULT_DB_PATH = "state/pm-agent.db"

# 有效发送状态（计入频控 / 幂等过滤的状态）
_EFFECTIVE_SEND_STATUSES = ("success", "mock")


class Store:
    """SQLite 封装，WAL 模式，首次运行自动建表。"""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        schema = _SCHEMA_PATH.read_text(encoding="utf-8")
        self._conn.executescript(schema)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── item_state ──

    def upsert_item_seen(self, item_id: str, now: str | None = None) -> None:
        """标记事项本次被扫到。"""
        ts = now or datetime.now().isoformat()
        self._conn.execute(
            """INSERT INTO item_state (item_id, last_seen_at)
               VALUES (?, ?)
               ON CONFLICT(item_id) DO UPDATE SET last_seen_at=excluded.last_seen_at,
                                                  vanished_at=NULL""",
            (item_id, ts),
        )
        self._conn.commit()

    def mark_vanished(self, item_id: str, now: str | None = None) -> None:
        ts = now or datetime.now().isoformat()
        self._conn.execute(
            "UPDATE item_state SET vanished_at=? WHERE item_id=?",
            (ts, item_id),
        )
        self._conn.commit()

    def get_item_state(self, item_id: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT item_id, last_seen_at, reminder_count, last_reminder_at, "
            "last_reminder_type, vanished_at FROM item_state WHERE item_id=?",
            (item_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "item_id": row[0],
            "last_seen_at": row[1],
            "reminder_count": row[2],
            "last_reminder_at": row[3],
            "last_reminder_type": row[4],
            "vanished_at": row[5],
        }

    def list_all_item_states(self) -> list[dict]:
        """返回全部 item_state 记录，通过 public API 暴露。"""
        cur = self._conn.execute(
            "SELECT item_id, last_seen_at, reminder_count, "
            "last_reminder_at, last_reminder_type, vanished_at "
            "FROM item_state"
        )
        return [
            {
                "item_id": r[0],
                "last_seen_at": r[1],
                "reminder_count": r[2],
                "last_reminder_at": r[3],
                "last_reminder_type": r[4],
                "vanished_at": r[5],
            }
            for r in cur.fetchall()
        ]

    def list_vanished(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT item_id, last_seen_at, vanished_at FROM item_state "
            "WHERE vanished_at IS NOT NULL"
        )
        return [
            {"item_id": r[0], "last_seen_at": r[1], "vanished_at": r[2]}
            for r in cur.fetchall()
        ]

    def get_all_item_ids(self) -> set[str]:
        cur = self._conn.execute("SELECT item_id FROM item_state")
        return {r[0] for r in cur.fetchall()}

    # ── follow_up_log ──

    def insert_follow_up(
        self,
        run_id: str,
        item_id: str,
        owner: str,
        welink_id: str,
        reminder_type: str,
        send_status: str,
        message: str,
        dedupe_key: str,
        error: str | None = None,
        now: str | None = None,
    ) -> int:
        ts = now or datetime.now().isoformat()
        cur = self._conn.execute(
            "INSERT INTO follow_up_log "
            "(run_id, item_id, owner, welink_id, reminder_type, send_status, "
            "message, dedupe_key, error, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, item_id, owner, welink_id, reminder_type,
             send_status, message, dedupe_key, error, ts),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def count_by_owner_today(self, welink_id: str, today: str | None = None) -> int:
        """统计某责任人当天已发送条数。"""
        d = today or date.today().isoformat()
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM follow_up_log "
            "WHERE welink_id=? AND created_at LIKE ? AND send_status IN (?,?)",
            (welink_id, f"{d}%", *_EFFECTIVE_SEND_STATUSES),
        )
        return cur.fetchone()[0]

    def count_run(self, run_id: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM follow_up_log "
            "WHERE run_id=? AND send_status IN (?,?)",
            (run_id, *_EFFECTIVE_SEND_STATUSES),
        )
        return cur.fetchone()[0]

    def exists_dedupe(self, dedupe_key: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM follow_up_log WHERE dedupe_key=? "
            "AND send_status IN (?,?) LIMIT 1",
            (dedupe_key, *_EFFECTIVE_SEND_STATUSES),
        )
        return cur.fetchone() is not None

    # ── decision_log ──

    def insert_decision(
        self,
        decision_id: str,
        run_id: str,
        decision_type: str,
        rationale: str,
        target_item_id: str | None = None,
        action_taken: str | None = None,
        now: str | None = None,
    ) -> None:
        ts = now or datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO decision_log "
            "(id, run_id, decision_type, target_item_id, rationale, action_taken, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (decision_id, run_id, decision_type, target_item_id, rationale, action_taken, ts),
        )
        self._conn.commit()

    # ── context_brief ──

    def insert_brief(
        self, run_id: str, brief: str, token_count: int, now: str | None = None
    ) -> None:
        ts = now or datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO context_brief (run_id, brief, token_count, created_at) "
            "VALUES (?,?,?,?)",
            (run_id, brief, token_count, ts),
        )
        self._conn.commit()

    def get_latest_brief(self) -> dict | None:
        cur = self._conn.execute(
            "SELECT id, run_id, brief, token_count, created_at "
            "FROM context_brief ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "run_id": row[1], "brief": row[2],
            "token_count": row[3], "created_at": row[4],
        }
