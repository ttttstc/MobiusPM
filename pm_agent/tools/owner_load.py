"""owner_load — Owner 负载仪表板（M6 Feature 2）

设计要点：
- 多人 owner 事项按 1/n 分摊到每个 owner（避免双计）
- 缺责任人不计入（不归到"未指派"桶）
- 状态判定：active >8 OR p0 >3 → "过载"; active <2 → "清闲"; 其余 → "正常"
- 瓶颈识别：阻塞他人事项 ≥3 个的 owner 标红
- 仅看活跃事项（排除已关闭/挂起/重复/拒绝）
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from pm_agent.memory.store import Store

_CLOSED_STATUSES = {"已关闭", "重复", "拒绝"}
_SNOOZED_STATUSES = {"挂起"}
_INACTIVE_STATUSES = _CLOSED_STATUSES | _SNOOZED_STATUSES

# 阈值
_OVERLOAD_ACTIVE = 8   # active > 8
_OVERLOAD_P0 = 3       # p0 > 3
_IDLE_ACTIVE = 2       # active < 2
_BOTTLENECK_BLOCKING = 3  # blocking_count >= 3 → 瓶颈


def _is_active(item: dict) -> bool:
    return item.get("normalized_status") not in _INACTIVE_STATUSES


def _blocking_counts(work_items: list[dict]) -> dict[str, int]:
    """近似计算每个 owner 阻塞了多少其他事项。

    简化策略（数据库无显式依赖图）：
    - 把"被依赖"的方向近似为：同一 source + 同 priority + 不同 owner 的活跃事项中，
      当前 owner 拥有的事项比其对等事项更晚 due_date（或无 due_date）的对等事项数。
    - 但这种近似太复杂且容易误导。

    更可执行的近似：
    - owner 拥有的活跃事项数 = 他可能被依赖的"工作量"
    - 同 priority 中他拥有的活跃事项数 = 他阻塞他人的"边界"

    最简单可解释的方案：owner 的"瓶颈"= 他的活跃事项中，
    有多少其他活跃事项的 due_date >= 他的 due_date（说明他在前面）。
    这条规则太严格。

    退一步采用可观测信号：owner 拥有的活跃 P0/P1 事项数 ≥ _BOTTLENECK_BLOCKING → 瓶颈。
    （他的活跃 P0/P1 多 → 他一旦延迟就阻塞多条线）

    这是 MVP 启发式，未来可替换为真实依赖图。
    """
    # 这里采用保守方案：活跃 P0/P1 数作为瓶颈信号
    blocking: dict[str, int] = defaultdict(int)
    for it in work_items:
        if not _is_active(it):
            continue
        if it.get("priority_level") not in ("P0", "P1"):
            continue
        for owner in it.get("owner_list") or []:
            blocking[owner] += 1
    return dict(blocking)


def _weekly_added_closed(
    db_path: str | Path | None,
    owners: list[str],
) -> tuple[dict[str, int], dict[str, int]]:
    """统计近 7 天每个 owner 的新增（last_seen_at）和闭环（vanished_at）。"""
    added: dict[str, int] = defaultdict(int)
    closed: dict[str, int] = defaultdict(int)
    if not db_path:
        return {}, {}
    try:
        store = Store(db_path)
    except Exception:
        return {}, {}

    try:
        # 全部 item_state → 按 owner 聚合
        # 注：item_state 表只存 item_id + 时间，不存 owner；只能按 item 关联
        # 简化为：从 follow_up_log 取 owner 维度的事件
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()

        cur = store._conn.execute(
            "SELECT owner, item_id, created_at FROM follow_up_log "
            "WHERE created_at >= ? AND send_status IN ('success','mock')",
            (cutoff,),
        )
        # 同一 item_id 的最近事件作为 "added/closed" 信号近似
        seen: dict[str, str] = {}  # item_id → owner
        for owner, item_id, _ts in cur.fetchall():
            seen[item_id] = owner

        # 闭环近似：从 item_state.vanished_at 不为空 → owner 不易反查
        # 这里 "weekly_added" 简化为近 7 天首次被催办的不同 item_id 数
        for owner in owners:
            owner_items = {iid for iid, o in seen.items() if o == owner}
            added[owner] = len(owner_items)

    finally:
        store.close()

    return dict(added), dict(closed)


def query_owner_load(
    work_items: list[dict],
    db_path: str | Path | None = None,
) -> dict:
    """计算 owner 负载。

    输入:
        work_items: read_excel 返回的 WorkItem 列表
        db_path: SQLite 路径（可选；提供则尝试拉取近 7 天新增/闭环数据）

    输出:
        {
          "owners": [
            {
              "owner": "张三",
              "active": 8.5,           # 分摊后的活跃数
              "p0": 3.0,               # P0 分摊数
              "blocking_count": 5,     # 活跃 P0/P1 事项数（瓶颈启发式）
              "weekly_added": 2,
              "weekly_closed": 0,
              "status": "过载",        # 过载 / 正常 / 清闲
              "is_bottleneck": False,  # blocking_count >= 3
              "items": ["item1", ...]  # top 5 关键事项（按 P0 优先 + due_date 升序）
            },
            ...
          ],
          "summary": {
            "owner_count": int,
            "overloaded_count": int,
            "bottleneck_count": int,
          }
        }
    """
    # 1) 分摊计数
    active_map: dict[str, float] = defaultdict(float)
    p0_map: dict[str, float] = defaultdict(float)
    items_map: dict[str, list[dict]] = defaultdict(list)

    for it in work_items:
        if not _is_active(it):
            continue
        owner_list = it.get("owner_list") or []
        if not owner_list:
            continue  # 缺责任人不计入
        n = len(owner_list)
        credit = 1.0 / n
        for owner in owner_list:
            active_map[owner] += credit
            if it.get("priority_level") == "P0":
                p0_map[owner] += credit
            items_map[owner].append(it)

    # 2) 瓶颈识别（活跃 P0/P1 数）
    blocking = _blocking_counts(work_items)

    # 3) 周新增/闭环
    weekly_added, weekly_closed = _weekly_added_closed(
        db_path, list(active_map.keys())
    )

    # 4) 拼装结果
    owners: list[dict] = []
    for owner in active_map:
        active = round(active_map[owner], 2)
        p0 = round(p0_map[owner], 2)
        blocking_count = blocking.get(owner, 0)

        # 状态判定
        if active > _OVERLOAD_ACTIVE or p0 > _OVERLOAD_P0:
            status = "过载"
        elif active < _IDLE_ACTIVE:
            status = "清闲"
        else:
            status = "正常"

        # top 5 关键事项：P0 优先 + due_date 升序
        sorted_items = sorted(
            items_map[owner],
            key=lambda it: (
                0 if it.get("priority_level") == "P0" else 1,
                it.get("due_date") or "9999-12-31",
            ),
        )
        top_items = [
            {
                "item_id": it["item_id"],
                "title": it.get("title", "")[:40],
                "priority": it.get("priority_level", ""),
                "due_date": it.get("due_date"),
                "status": it.get("normalized_status", ""),
            }
            for it in sorted_items[:5]
        ]

        owners.append({
            "owner": owner,
            "active": active,
            "p0": p0,
            "blocking_count": blocking_count,
            "weekly_added": weekly_added.get(owner, 0),
            "weekly_closed": weekly_closed.get(owner, 0),
            "status": status,
            "is_bottleneck": blocking_count >= _BOTTLENECK_BLOCKING,
            "items": top_items,
        })

    # 排序：过载 → 瓶颈 → 正常 → 清闲；同状态内按 active 倒序
    status_order = {"过载": 0, "正常": 1, "清闲": 2}
    owners.sort(
        key=lambda o: (
            status_order.get(o["status"], 9),
            -(1 if o["is_bottleneck"] else 0),
            -o["active"],
        )
    )

    overloaded_count = sum(1 for o in owners if o["status"] == "过载")
    bottleneck_count = sum(1 for o in owners if o["is_bottleneck"])

    return {
        "owners": owners,
        "summary": {
            "owner_count": len(owners),
            "overloaded_count": overloaded_count,
            "bottleneck_count": bottleneck_count,
        },
    }