"""Agent loop 核心 — Claude Agent SDK 集成（M2）"""
from __future__ import annotations

import importlib
import json
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from pm_agent.config import load_config
from pm_agent.memory.loader import load_initial_context
from pm_agent.memory.store import Store
from pm_agent.tools import TOOL_REGISTRY, TOOL_SCHEMAS

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def _load_system_prompt(cron_mode: bool = False) -> str:
    base = _PROMPT_DIR.joinpath("system.md").read_text(encoding="utf-8")
    if cron_mode:
        base += (
            "\n\n## ⚠️ 当前模式：CRON（无人值守）\n\n"
            "PM 不在场。你**绝对不能**调 ask_human 或 send_welink。\n"
            "你应该：读表 → 分析规则 → 写决策 → 写 brief → 退出。\n"
            "把需要确认的候选留给 PM 下次 wake 时查看。"
        )
    return base


def _call_tool(name: str, args: dict, injected: dict | None = None) -> Any:
    """动态调用工具函数。injected 用于注入 run_id / notifier 等运行时依赖。"""
    fq_name = TOOL_REGISTRY.get(name)
    if not fq_name:
        return {"error": f"unknown tool: {name}"}

    mod_path, func_name = fq_name.rsplit(".", 1)
    mod = importlib.import_module(mod_path)
    func = getattr(mod, func_name)

    merged = {**args}
    if injected:
        merged.update(injected)

    return func(**merged)


class AgentRunLogger:
    """将每轮 LLM + tool 调用写入 jsonl。"""

    def __init__(self, log_path: str):
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(str(self._path), "w", encoding="utf-8")

    def log(self, entry: dict) -> None:
        entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._fd.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fd.flush()

    def close(self) -> None:
        self._fd.close()


def run_agent(
    trigger_reason: str = "wake",
    system_prompt: str | None = None,
    api_key: str | None = None,
    model: str = "claude-opus-4-7",
    max_tokens: int = 4096,
    max_tokens_per_loop: int = 50000,
    db_path: str = "state/pm-agent.db",
    excel_path: str = "source/项目630流水线排期计划.xlsx",
    sheet_name: str = "630攻关问题清单",
    contacts: dict | None = None,
) -> dict:
    """
    主 agent loop。

    返回 {"run_id": str, "total_tokens": int, "iterations": int, "brief_written": bool}
    """
    run_id = f"{trigger_reason}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cron_mode = trigger_reason == "cron"

    # Logger
    log_dir = Path("state/agent_runs")
    logger = AgentRunLogger(str(log_dir / f"{run_id}.jsonl"))

    # System prompt
    sys_prompt = system_prompt or _load_system_prompt(cron_mode)

    # Initial user message（含跨周期记忆）
    initial_user = load_initial_context(
        trigger_reason=trigger_reason,
        db_path=db_path,
    )

    # Anthropic client
    client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY", ""))

    messages: list[dict] = [{"role": "user", "content": initial_user}]
    total_input_tokens = 0
    total_output_tokens = 0
    iterations = 0
    brief_written = False

    # 工具注入参数
    tool_inject = {
        "run_id": run_id,
        "excel_path": excel_path,
        "sheet_name": sheet_name,
        "db_path": db_path,
        "contacts": contacts,
    }

    # 确认 token 跟踪
    from pm_agent.tools.notifier import store_confirmation_token

    store = Store(db_path)

    try:
        while True:
            iterations += 1

            if total_input_tokens + total_output_tokens >= max_tokens_per_loop:
                # 超出上限，写 brief 后强制退出
                _force_end(client, model, messages, total_input_tokens + total_output_tokens,
                          store, run_id, logger)
                brief_written = True
                break

            # LLM 调用
            llm_start = time.time()
            resp = client.messages.create(
                model=model,
                system=sys_prompt,
                tools=TOOL_SCHEMAS,
                messages=messages,
                max_tokens=max_tokens,
            )
            llm_elapsed = time.time() - llm_start

            total_input_tokens += resp.usage.input_tokens
            total_output_tokens += resp.usage.output_tokens

            logger.log({
                "event": "llm_call",
                "iteration": iterations,
                "stop_reason": resp.stop_reason,
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "elapsed_s": round(llm_elapsed, 2),
                "content": [
                    {"type": b.type, "text": getattr(b, "text", None) or str(b)}
                    for b in resp.content
                ],
            })

            # 追加 assistant 消息
            messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "end_turn":
                # agent 完成任务
                print(f"\n[agent] end_turn · {iterations} iterations · "
                      f"{total_input_tokens + total_output_tokens} tokens")
                break

            if resp.stop_reason == "tool_use":
                tool_results: list[dict] = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue

                    tool_name = block.name
                    tool_args = block.input or {}
                    print(f"  [tool] {tool_name}({_brief_args(tool_args)})")
                    logger.log({
                        "event": "tool_call",
                        "name": tool_name,
                        "args": tool_args,
                    })

                    # 执行工具
                    try:
                        # cron 模式下禁用 ask_human / send_welink
                        if cron_mode and tool_name in ("ask_human", "send_welink"):
                            result = {"status": "unavailable", "reason": "cron_mode",
                                      "message": "PM 不在场，不能发送消息。请改为写 decision 记录此判断。"}
                            logger.log({"event": "tool_result", "name": tool_name, "success": False, "result": result})
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False),
                            })
                            continue

                        # 执行
                        result = _call_tool(tool_name, tool_args, tool_inject)
                        success = True

                        # 检测 brief 是否已写
                        if tool_name == "update_context_brief" and result.get("status") == "ok":
                            brief_written = True

                        logger.log({
                            "event": "tool_result",
                            "name": tool_name,
                            "success": True,
                            "result_snippet": str(result)[:500],
                        })

                    except Exception as e:
                        success = False
                        result = {"error": str(e), "traceback": traceback.format_exc()}
                        logger.log({
                            "event": "tool_result",
                            "name": tool_name,
                            "success": False,
                            "error": str(e),
                        })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                messages.append({"role": "user", "content": tool_results})

            else:
                _fallback_log(messages, resp, logger)
                break

    except KeyboardInterrupt:
        print("\n[agent] interrupted by user")
    finally:
        store.close()
        logger.close()

    return {
        "run_id": run_id,
        "total_tokens": total_input_tokens + total_output_tokens,
        "iterations": iterations,
        "brief_written": brief_written,
    }


def _force_end(
    client: Anthropic,
    model: str,
    messages: list[dict],
    token_used: int,
    store: Store,
    run_id: str,
    logger: AgentRunLogger,
) -> None:
    """Token 超限时，强制让 agent 写 brief 后退出。"""
    force_msg = (
        f"Token 预算已用 {token_used}，接近上限。"
        "请立即调用 update_context_brief 写简要摘要，然后直接结束。"
        "不要做其他操作。"
    )
    messages.append({"role": "user", "content": force_msg})
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=TOOL_SCHEMAS[-1:],  # 只给 update_context_brief
            messages=messages,
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == "update_context_brief":
                try:
                    from pm_agent.tools.state import update_context_brief

                    update_context_brief(
                        brief=(block.input or {}).get("brief", "Budget exceeded"),
                        run_id=run_id,
                    )
                except Exception:
                    pass
        logger.log({"event": "force_end", "tokens_used": token_used})
    except Exception:
        # 无论如何写一条 brief
        store.insert_brief(run_id, f"Budget exceeded at {token_used} tokens", token_used)


def _brief_args(args: dict) -> str:
    """工具参数摘要（打印到 stderr）。"""
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 40:
            s = s[:37] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)


def _fallback_log(messages: list, resp: Any, logger: AgentRunLogger) -> None:
    print(f"[agent] unexpected stop_reason: {resp.stop_reason}")
    logger.log({"event": "unexpected_stop", "stop_reason": str(resp.stop_reason)})
