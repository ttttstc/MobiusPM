from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class WorkItem:
    """PRD §15.1 WorkItem，字段名 Python snake_case。"""

    item_id: str
    sheet_name: str
    row_index: int
    raw_no: str | None  # 原始序号，可能是 '146-1' 这种非纯数字值
    title: str
    raw_issue_status: str  # Open / Close / ''
    source: str
    issue: str | None
    priority_raw: str
    priority_level: str  # P0 / P1 / P2 / Ignore
    handler_chain: list[str]
    owner_raw: str | None
    owner_list: list[str]
    support_status: str
    normalized_status: str
    due_date: str | None  # ISO date string or None
    remark: str | None
    reminder_count: int = 0

    def to_dict(self) -> dict:
        """转为 JSON-serializable dict。"""
        return asdict(self)
