"""trend — 进度趋势 + 扫描差异（M6 Feature 1）

设计要点：
- 每次 wake 写一个 snapshot 到 state/trend/{date}_{run_id}.json
- snapshot 文件只能写不能改（不可覆盖），用于永久可追溯
- trend 判定只用 1 个比较点：当前 run vs 最近 1 次 run（避免老数据干扰判断）
- diff 阈值保守：>3 项变化才计为恶化，避免抖动
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

_TREND_DIR = Path("state/trend")

# 阈值：变化超过此数才计为恶化（避免抖动）
_DELTA_THRESHOLD = 3

_CLOSED_STATUSES = {"已关闭", "重复", "拒绝"}
_SNOOZED_STATUSES = {"挂起"}


def _snapshot_filename(run_id: str, today: str | None = None) -> str:
    d = today or date.today().isoformat()
    safe_run = run_id.replace("/", "_").replace("..", "_")
    return f"{d}_{safe_run}.json"


def _build_snapshot(
    work_items: list[dict],
    suggestions: list[dict],
    run_id: str,
) -> dict:
    """从 work_items + suggestions 提取快照指标。"""
    total = len(work_items)
    active = sum(
        1 for it in work_items if it.get("normalized_status") not in _CLOSED_STATUSES
    )
    closed = total - active
    high_risk = sum(1 for s in suggestions if s["severity"] == "high")
    today = date.today().isoformat()
    overdue = sum(
        1 for it in work_items
        if it.get("due_date")
        and it["due_date"] < today
        and it.get("normalized_status") not in (_CLOSED_STATUSES | _SNOOZED_STATUSES)
    )

    by_priority: dict[str, int] = {}
    for it in work_items:
        p = it.get("priority_level") or "无"
        by_priority[p] = by_priority.get(p, 0) + 1

    by_status: dict[str, int] = {}
    for it in work_items:
        s = it.get("normalized_status") or "未知"
        by_status[s] = by_status.get(s, 0) + 1

    owner_set: set[str] = set()
    for it in work_items:
        for o in it.get("owner_list") or []:
            owner_set.add(o)

    return {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "active": active,
        "closed": closed,
        "high_risk": high_risk,
        "overdue": overdue,
        "by_priority": by_priority,
        "by_status": by_status,
        "by_owner_count": len(owner_set),
    }


def record_snapshot(
    work_items: list[dict],
    suggestions: list[dict],
    run_id: str,
    trend_dir: str | Path = _TREND_DIR,
) -> dict:
    """记录一次 wake 的快照到磁盘。

    输入:
        work_items: read_excel 返回的 WorkItem 列表
        suggestions: query_rule_suggestions 返回的建议列表
        run_id: 本次运行 ID
        trend_dir: 快照目录（默认 state/trend）

    输出:
        {"status": "ok", "path": str, "size_bytes": int, "snapshot": dict}
    """
    snapshot = _build_snapshot(work_items, suggestions, run_id)
    trend_dir = Path(trend_dir)
    trend_dir.mkdir(parents=True, exist_ok=True)
    file_name = _snapshot_filename(run_id)
    out_path = trend_dir / file_name

    payload = json.dumps(snapshot, ensure_ascii=False, indent=2)
    out_path.write_text(payload, encoding="utf-8")

    return {
        "status": "ok",
        "path": str(out_path),
        "size_bytes": out_path.stat().st_size,
        "snapshot": snapshot,
    }


def _list_snapshots(trend_dir: Path, exclude_run_id: str | None = None) -> list[Path]:
    """列出 trend_dir 下所有 snapshot 文件，按文件名（日期+run_id）排序。"""
    if not trend_dir.exists():
        return []
    files = [
        p for p in trend_dir.iterdir()
        if p.is_file() and p.suffix == ".json"
    ]
    files.sort(key=lambda p: p.name)
    if exclude_run_id:
        files = [p for p in files if exclude_run_id not in p.name]
    return files


def _load_snapshot(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _compute_diff(current: dict, previous: dict) -> dict:
    """对比当前 vs 上次的指标变化。"""
    keys = ["total", "active", "closed", "high_risk", "overdue"]
    diff: dict[str, dict] = {}
    for k in keys:
        cur = current.get(k, 0)
        prev = previous.get(k, 0)
        delta = cur - prev
        diff[k] = {"current": cur, "previous": prev, "delta": delta}

    # by_priority / by_status 增量（仅列有变化的 key）
    def _dict_delta(a: dict, b: dict) -> dict[str, dict]:
        result: dict[str, dict] = {}
        keys_all = set(a) | set(b)
        for k in keys_all:
            ac = a.get(k, 0)
            bc = b.get(k, 0)
            if ac != bc:
                result[k] = {"current": ac, "previous": bc, "delta": ac - bc}
        return result

    diff["by_priority_delta"] = _dict_delta(
        current.get("by_priority", {}), previous.get("by_priority", {})
    )
    diff["by_status_delta"] = _dict_delta(
        current.get("by_status", {}), previous.get("by_status", {})
    )
    return diff


def _verdict(diff: dict, prev_time: str | None = None) -> dict:
    """根据 diff 给出趋势判定。

    规则（保守阈值 _DELTA_THRESHOLD = 3）：
      - high_risk 增加 >3 → 恶化
      - overdue 增加 >3 → 恶化
      - active 减少 >3（说明闭环多） + high_risk 不增 → 好转
      - active 增加 >3（说明新增多） + high_risk 同增 → 恶化
      - 其它 → 持平
    """
    high_delta = diff["high_risk"]["delta"]
    overdue_delta = diff["overdue"]["delta"]
    active_delta = diff["active"]["delta"]

    bad_score = max(0, high_delta) + max(0, overdue_delta)
    good_score = max(0, -active_delta)  # active 减少 = 闭环 = 好

    if bad_score >= _DELTA_THRESHOLD:
        direction = "恶化"
        glyph = "●"
    elif good_score >= _DELTA_THRESHOLD and high_delta <= 0:
        direction = "好转"
        glyph = "■"
    elif abs(high_delta) <= 1 and abs(overdue_delta) <= 1:
        direction = "持平"
        glyph = "▲"
    elif bad_score > good_score:
        direction = "恶化"
        glyph = "●"
    else:
        direction = "好转"
        glyph = "■"

    return {
        "direction": direction,
        "glyph": glyph,
        "high_delta": high_delta,
        "overdue_delta": overdue_delta,
        "active_delta": active_delta,
        "previous_run_id": prev_time,
    }


def query_trend(
    run_id: str,
    trend_dir: str | Path = _TREND_DIR,
) -> dict:
    """查询本次 vs 上次 snapshot 的对比 + 趋势判定。

    输入:
        run_id: 本次运行 ID（用于从同 run_id 的旧 snapshot 中排除；新 snapshot 不必已存在）
        trend_dir: 快照目录

    输出:
        {
          "status": "ok",
          "snapshot": 当前 snapshot（若已存在）或 None,
          "previous": 最近一次 snapshot,
          "diff": {指标: {current, previous, delta}, ...},
          "verdict": {direction, glyph, ...},
          "snapshots_total": 当前 trend 目录中 snapshot 总数
        }
    """
    trend_dir = Path(trend_dir)
    files = _list_snapshots(trend_dir)

    # 当前 snapshot：按 run_id + 今天日期找
    today_str = date.today().isoformat()
    current_path = trend_dir / _snapshot_filename(run_id, today_str)
    current = _load_snapshot(current_path) if current_path.exists() else None

    # 上次 snapshot：找最近一次不同 run_id 的 snapshot
    previous: dict | None = None
    previous_path: Path | None = None
    for p in reversed(files):
        if current_path.exists() and p == current_path:
            continue
        prev = _load_snapshot(p)
        if prev:
            previous = prev
            previous_path = p
            break

    if current is None:
        return {
            "status": "ok",
            "snapshot": None,
            "previous": previous,
            "diff": None,
            "verdict": {
                "direction": "首次运行",
                "glyph": "■",
                "previous_run_id": previous.get("run_id") if previous else None,
                "previous_timestamp": previous.get("timestamp") if previous else None,
            },
            "snapshots_total": len(files),
            "previous_path": str(previous_path) if previous_path else None,
        }

    if previous is None:
        return {
            "status": "ok",
            "snapshot": current,
            "previous": None,
            "diff": None,
            "verdict": {
                "direction": "首次对比",
                "glyph": "■",
                "previous_run_id": None,
            },
            "snapshots_total": len(files),
            "previous_path": None,
        }

    diff = _compute_diff(current, previous)
    verdict = _verdict(diff, previous.get("run_id"))
    verdict["previous_timestamp"] = previous.get("timestamp")

    return {
        "status": "ok",
        "snapshot": current,
        "previous": previous,
        "diff": diff,
        "verdict": verdict,
        "snapshots_total": len(files),
        "previous_path": str(previous_path),
    }