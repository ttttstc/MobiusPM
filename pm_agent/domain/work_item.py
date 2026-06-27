from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WorkItem:
    """PRD §15.1 WorkItem，字段名 Python snake_case。"""

    item_id: str
    sheet_name: str
    row_index: int
    raw_no: Optional[str]  # 原始序号，可能是 '146-1' 这种非纯数字值
    title: str
    raw_issue_status: str  # Open / Close / ''
    source: str
    issue: Optional[str]
    priority_raw: str
    priority_level: str  # P0 / P1 / P2 / Ignore
    handler_chain: list[str]
    owner_raw: Optional[str]
    owner_list: list[str]
    support_status: str
    normalized_status: str
    due_date: Optional[str]  # ISO date string or None
    remark: Optional[str]
    reminder_count: int = 0

    def to_dict(self) -> dict:
        """转为 JSON-serializable dict。"""
        return {
            "item_id": self.item_id,
            "sheet_name": self.sheet_name,
            "row_index": self.row_index,
            "raw_no": self.raw_no,
            "title": self.title,
            "raw_issue_status": self.raw_issue_status,
            "source": self.source,
            "issue": self.issue,
            "priority_raw": self.priority_raw,
            "priority_level": self.priority_level,
            "handler_chain": self.handler_chain,
            "owner_raw": self.owner_raw,
            "owner_list": self.owner_list,
            "support_status": self.support_status,
            "normalized_status": self.normalized_status,
            "due_date": self.due_date,
            "remark": self.remark,
            "reminder_count": self.reminder_count,
        }
