from __future__ import annotations

# PRD §8 状态映射全表
# key = (问题状态, 支持情况) → 标准状态
# 问题状态和支持情况做 strip() 后查表
_STATUS_MAP: dict[tuple[str, str], str] = {
    ("Open", "待验收"): "待验收",
    ("Close", "待验收"): "待验收待关闭",
    ("Open", "已完成"): "完成待关闭",
    ("Close", "已完成"): "已关闭",
    ("Open", "开发中"): "开发中",
    ("Open", "待排期"): "待排期",
    ("Open", "挂起(630后分析)"): "挂起",
    ("Open", "重复单"): "重复",
    ("Open", "拒绝"): "拒绝",
    ("Close", "拒绝"): "拒绝",
}

# 优先级映射
_PRIORITY_MAP: dict[str, str] = {
    "必备(630前)": "P0",
    "增强(争取630)": "P1",
    "长期演进(630后)": "P2",
    "拒绝(不处理)": "Ignore",
}


def map_status(issue_status: str, support_status: str) -> str:
    """从 问题状态 + 支持情况 映射标准状态。未知组合返回 '未知'。"""
    return _STATUS_MAP.get(
        (issue_status.strip(), support_status.strip()), "未知"
    )


def map_priority(raw: str) -> str:
    """从原始优先级文本映射 P0/P1/P2/Ignore。未知返回 'P2'。"""
    return _PRIORITY_MAP.get(raw.strip(), "P2")
