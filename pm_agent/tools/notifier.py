"""send_welink tool + WeLinkNotifier 接口 + MockNotifier（P2 安全边界强制）"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from pm_agent.memory.store import DEFAULT_DB_PATH, Store
from pm_agent.tools.safety import check_rate_limit, check_run_limit, dedupe_key


class WeLinkNotifier(Protocol):
    """WeLink 发送适配器接口。"""

    def send(self, to: str, message: str) -> dict:
        """
        返回 {"success": bool, "message_id": str | None, "error": str | None}
        """
        ...


class MockNotifier:
    """Mock 实现：写 mock_sent.jsonl，默认返回 success。"""

    def __init__(self, output_path: str | Path = "state/mock_sent.jsonl"):
        self._output = Path(output_path)
        self._output.parent.mkdir(parents=True, exist_ok=True)

    def send(self, to: str, message: str) -> dict:
        entry = {
            "to": to,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "message_id": f"mock_{datetime.now().timestamp():.0f}",
        }
        with open(self._output, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"success": True, "message_id": entry["message_id"], "error": None}


class WeLinkCliNotifier:
    """真实 WeLink CLI 发送器 — 调用外部 welink 命令发送消息。"""

    def __init__(
        self,
        cli_path: str = "welink",
        timeout: int = 30,
        retry_count: int = 1,
    ):
        self._cli = cli_path
        self._timeout = timeout
        self._retry = retry_count

    def send(self, to: str, message: str) -> dict:
        import subprocess
        import time

        last_error = None
        for attempt in range(self._retry + 1):
            try:
                result = subprocess.run(
                    [self._cli, "send", "--to", to, "--message", message],
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
                if result.returncode == 0:
                    return {
                        "success": True,
                        "message_id": result.stdout.strip() or f"wl_{int(time.time())}",
                        "error": None,
                    }
                last_error = result.stderr.strip() or f"exit code {result.returncode}"
            except subprocess.TimeoutExpired:
                last_error = f"timeout after {self._timeout}s"
            except FileNotFoundError:
                last_error = f"welink CLI not found at {self._cli}"
                break
            except Exception as e:
                last_error = str(e)

        return {"success": False, "message_id": None, "error": last_error}


# ── 内存中的 confirmation token 存储（本次 loop 有效）──
_pending_tokens: dict[str, str] = {}  # run_id → token


def store_confirmation_token(run_id: str, token: str) -> None:
    _pending_tokens[run_id] = token


def clear_confirmation_token(run_id: str) -> None:
    _pending_tokens.pop(run_id, None)


# ── send_welink tool ──


def send_welink(
    item_id: str,
    owner: str,
    welink_id: str,
    message: str,
    reminder_type: str,
    confirmation_token: str,
    run_id: str,
    notifier: WeLinkNotifier | None = None,
    contacts: dict[str, dict] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    max_per_owner_per_day: int = 5,
    max_per_run: int = 50,
) -> dict:
    """
    发送 WeLink 消息。

    内部强制安全检查（P2 原则），LLM 绕不过：
    1. 幂等: 同 dedupe_key 已成功 → blocked
    2. 频控: 单责任人当天超限 → rate_limited
    3. 运行上限: 单次 run 超限 → run_limit
    4. 白名单: 联系人未启用 → not_whitelisted
    5. confirmation_token: 必须匹配 ask_human 返回的 token

    返回:
        {status: "sent"|"blocked"|"error", reason: str, ...}
    """
    store = Store(db_path)
    try:
        today = date.today().isoformat()

        # 1. 幂等检查
        dk = dedupe_key(item_id, reminder_type, today)
        if store.exists_dedupe(dk):
            return {"status": "blocked", "reason": "dedupe", "dedupe_key": dk}

        # 2. 单责任人当天上限
        rate = check_rate_limit(welink_id, today=today, max_per_day=max_per_owner_per_day, db_path=db_path)
        if not rate["allowed"]:
            return {"status": "blocked", "reason": "rate_limited",
                    "current": rate["current"], "limit": rate["limit"]}

        # 3. 单次运行上限
        run_r = check_run_limit(run_id, max_per_run=max_per_run, db_path=db_path)
        if not run_r["allowed"]:
            return {"status": "blocked", "reason": "run_limit",
                    "current": run_r["current"], "limit": run_r["limit"]}

        # 4. 白名单检查
        if contacts:
            c = contacts.get(owner)
            if c is None:
                # 尝试 aliases
                for cname, cdata in contacts.items():
                    if owner in cdata.get("aliases", []):
                        c = cdata
                        break
            if c is None:
                return {"status": "blocked", "reason": "not_whitelisted",
                        "detail": f"联系人 {owner} 未在 contacts.yaml 中"}
            if not c.get("enabled", True):
                return {"status": "blocked", "reason": "not_whitelisted",
                        "detail": f"联系人 {owner} 未启用"}

        # 5. confirmation_token 校验
        expected = _pending_tokens.get(run_id)
        if expected is None or confirmation_token != expected:
            return {"status": "error", "reason": "no_confirmation_token"}

        # 实际发送
        n = notifier or MockNotifier()
        result = n.send(to=welink_id, message=message)

        if result.get("success"):
            send_status = "mock" if isinstance(n, MockNotifier) else "success"
            store.insert_follow_up(
                run_id=run_id,
                item_id=item_id,
                owner=owner,
                welink_id=welink_id,
                reminder_type=reminder_type,
                send_status=send_status,
                message=message,
                dedupe_key=dk,
                error=result.get("error"),
            )
            return {"status": "sent", "dedupe_key": dk,
                    "message_id": result.get("message_id")}
        else:
            store.insert_follow_up(
                run_id=run_id,
                item_id=item_id,
                owner=owner,
                welink_id=welink_id,
                reminder_type=reminder_type,
                send_status="failed",
                message=message,
                dedupe_key=dk,
                error=result.get("error"),
            )
            return {"status": "error", "reason": "send_failed",
                    "error": result.get("error")}
    finally:
        store.close()
