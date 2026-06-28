from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import openpyxl

from pm_agent.domain.item_id import make_item_id
from pm_agent.domain.status_mapper import map_priority, map_status
from pm_agent.domain.work_item import WorkItem

# 多责任人分隔符：/、顿号、逗号（半角/全角）
_OWNER_SEP = re.compile(r"[/、,，]")

# 优先级映射（raw → level）在 status_mapper 中

# 默认主表名
_DEFAULT_SHEET = "630攻关问题清单"

# Excel 列索引（0-based）
COL_NO = 0  # 序号
COL_TITLE = 1  # 用户问题原文
COL_ISSUE_STATUS = 2  # 问题状态
COL_SOURCE = 3  # 来源
COL_ISSUE = 4  # issue
COL_PRIORITY = 5  # 优先级
COL_HANDLER = 6  # 当前处理方(依次依赖)
COL_OWNER = 7  # 责任人
COL_SUPPORT = 8  # 支持情况
COL_DUE = 9  # 计划时间
COL_REMARK = 10  # 说明


def read_excel(
    excel_path: str | Path,
    sheet_name: str = _DEFAULT_SHEET,
) -> dict:
    """
    只读模式读取 Excel 主表，返回标准化 WorkItem 列表。

    返回 JSON-serializable dict:
    {
        "items": [WorkItem.to_dict(), ...],
        "count": int,
        "vanished_item_ids": [str, ...],  # 本次未扫到但 SQLite 有的
        "sheet_name": str,
    }

    强约束：主表全程只读，运行前后 mtime 不变。
    """
    excel_path = Path(excel_path)
    initial_mtime = excel_path.stat().st_mtime

    wb = openpyxl.load_workbook(str(excel_path), read_only=True, data_only=True)
    try:
        ws = wb[sheet_name]
        items: list[WorkItem] = []

        for row_idx, row in enumerate(
            ws.iter_rows(min_row=2, values_only=True), start=2
        ):
            # 跳过空行（无用户问题原文）
            title = row[COL_TITLE]
            if title is None:
                continue

            title = str(title).strip()
            if not title:
                continue

            # raw_no 可能是非纯数字（如 '146-1'），保留原始字符串
            raw_no = row[COL_NO]
            raw_no_str: str | None = None
            if raw_no is not None:
                raw_no_str = str(raw_no).strip()
            raw_issue_status = str(row[COL_ISSUE_STATUS] or "").strip()
            source = str(row[COL_SOURCE] or "").strip()
            issue = str(row[COL_ISSUE]).strip() if row[COL_ISSUE] else None
            priority_raw = str(row[COL_PRIORITY] or "").strip()
            handler_raw = str(row[COL_HANDLER] or "").strip()
            owner_raw = str(row[COL_OWNER] or "").strip() if row[COL_OWNER] else None
            support_status = str(row[COL_SUPPORT] or "").strip()
            due_raw = row[COL_DUE]
            remark = str(row[COL_REMARK]).strip() if row[COL_REMARK] else None

            # 处理方拆分
            handler_chain = (
                [h.strip() for h in _OWNER_SEP.split(handler_raw) if h.strip()]
                if handler_raw
                else []
            )

            # 多责任人拆分
            if owner_raw:
                owner_list = [
                    o.strip() for o in _OWNER_SEP.split(owner_raw) if o.strip()
                ]
            else:
                owner_list = []

            # 日期处理：openpyxl 直接读出 datetime
            due_date: str | None = None
            if due_raw is not None:
                if isinstance(due_raw, datetime):
                    due_date = due_raw.date().isoformat()
                else:
                    # 万一遇到非 datetime 类型，尝试解析
                    try:
                        due_date = str(due_raw).strip() or None
                    except Exception:
                        due_date = None

            # 映射
            priority_level = map_priority(priority_raw)
            normalized_status = map_status(raw_issue_status, support_status)
            item_id = make_item_id(source, title)

            item = WorkItem(
                item_id=item_id,
                sheet_name=sheet_name,
                row_index=row_idx,
                raw_no=raw_no_str,
                title=title,
                raw_issue_status=raw_issue_status,
                source=source,
                issue=issue,
                priority_raw=priority_raw,
                priority_level=priority_level,
                handler_chain=handler_chain,
                owner_raw=owner_raw,
                owner_list=owner_list,
                support_status=support_status,
                normalized_status=normalized_status,
                due_date=due_date,
                remark=remark,
                reminder_count=0,
            )
            items.append(item)

    finally:
        wb.close()

    # mtime 不变校验（不用 assert，python -O 会剥离）
    final_mtime = excel_path.stat().st_mtime
    if initial_mtime != final_mtime:
        raise RuntimeError(
            f"Excel mtime changed! before={initial_mtime}, after={final_mtime}"
        )

    return {
        "items": [it.to_dict() for it in items],
        "count": len(items),
        "vanished_item_ids": [],  # 由调用方（debug CLI）与 SQLite 比对填充
        "sheet_name": sheet_name,
    }
