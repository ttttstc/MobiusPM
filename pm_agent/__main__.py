"""CLI 入口：python -m pm_agent <command>"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path

import yaml

from pm_agent.config import load_config


def cmd_debug(args: argparse.Namespace) -> None:
    cfg = load_config()
    excel_path = Path(cfg["excel"]["path"])
    sheet_name = cfg["excel"]["sheet"]
    db_path = Path(cfg["memory"]["db_path"])

    if args.tool == "read_excel":
        from pm_agent.tools.excel import read_excel

        result = read_excel(excel_path, sheet_name)
        if db_path.exists():
            from pm_agent.memory.store import Store

            store = Store(db_path)
            existing_ids = store.get_all_item_ids()
            current_ids = {it["item_id"] for it in result["items"]}
            result["vanished_item_ids"] = sorted(existing_ids - current_ids)
            store.close()

        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    elif args.tool == "query_state":
        from pm_agent.tools.state import query_state

        result = query_state(item_id=args.item_id, db_path=db_path)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    elif args.tool == "query_history":
        from pm_agent.tools.state import query_history

        result = query_history(item_id=args.item_id or "", max_records=args.max_records or 10, db_path=db_path)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    elif args.tool == "safety":
        from pm_agent.tools.safety import check_rate_limit, check_run_limit, dedupe_key

        if args.subtool == "dedupe_key":
            result = {"key": dedupe_key(args.item_id or "test", args.reminder_type or "test")}
        elif args.subtool == "check_rate_limit":
            result = check_rate_limit(args.welink_id or "test", db_path=db_path)
        elif args.subtool == "check_run_limit":
            result = check_run_limit(args.run_id or "test", db_path=db_path)
        else:
            print(f"Unknown subtool: {args.subtool}", file=sys.stderr)
            sys.exit(1)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    else:
        print(f"Unknown tool: {args.tool}", file=sys.stderr)
        sys.exit(1)


def cmd_wake(args: argparse.Namespace) -> None:
    """wake 模式：有 PM 在场，可对话确认 + mock 发送。"""
    cfg = load_config(args.config)

    # dry-run 模式不需要 API key，先检查
    if args.dry_run:
        _dry_run_wake(cfg)
        return

    api_key = cfg["llm"]["api_key"]
    if not api_key:
        print("错误: 未设置 ANTHROPIC_API_KEY。请设置环境变量或在配置文件中填入 api_key。", file=sys.stderr)
        sys.exit(1)

    model = args.model or cfg["llm"]["model"]
    base_url = args.base_url or cfg["llm"].get("base_url")
    max_tokens = args.max_tokens or cfg["llm"]["max_tokens"]
    max_tokens_per_loop = args.budget or cfg["llm"]["max_tokens_per_loop"]

    # Contacts
    contacts = None
    contacts_path = Path("config/contacts.yaml")
    if contacts_path.exists():
        from pm_agent.tools.contacts import load_contacts as lc

        contacts = lc(contacts_path)

    print("=" * 60)
    print("MobiusPM Agent · wake 模式")
    print(f"模型: {model}  |  单次上限: {max_tokens}  |  总预算: {max_tokens_per_loop}")
    print("=" * 60)

    from pm_agent.agent import run_agent

    result = run_agent(
        trigger_reason="wake",
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        max_tokens_per_loop=max_tokens_per_loop,
        db_path=cfg["memory"]["db_path"],
        excel_path=cfg["excel"]["path"],
        sheet_name=cfg["excel"]["sheet"],
        contacts=contacts,
    )

    print(f"\nrun_id: {result['run_id']}")
    print(f"tokens: {result['total_tokens']} ({result['iterations']} iterations)")
    print(f"brief: {'written' if result['brief_written'] else 'NOT written'}")


def _dry_run_wake(cfg: dict) -> None:
    """不调 LLM，直接跑全流程（用于 M1-B 级联工具验证）。"""
    from pm_agent.tools.excel import read_excel
    from pm_agent.tools.rules import query_rule_suggestions
    from pm_agent.tools.human import ask_human
    from pm_agent.tools.messages import gen_message
    from pm_agent.tools.notifier import send_welink
    from pm_agent.tools.state import write_decision, update_context_brief
    from pm_agent.tools.contacts import load_contacts as lc

    excel_path = Path(cfg["excel"]["path"])
    sheet_name = cfg["excel"]["sheet"]
    contacts_path = Path("config/contacts.yaml")
    contacts = lc(contacts_path) if contacts_path.exists() else None
    run_id = "dry_run_local"

    print("[dry_run] read_excel ...")
    r = read_excel(excel_path, sheet_name)
    print(f"  {r['count']} items")

    print("[dry_run] query_rule_suggestions ...")
    s = query_rule_suggestions(r["items"])
    print(f"  {s['count']} suggestions, by_rule={s['summary']['by_rule']}")

    print("[dry_run] ask_human (auto_yes) ...")
    candidates = s["suggestions"][:5]
    human = ask_human(candidates, run_id="dry_run_local", auto_yes=True)
    print(f"  confirmed: {len(human['confirmed_item_ids'])}")

    sent = 0
    for item_id in human["confirmed_item_ids"][:3]:
        it = next((i for i in r["items"] if i["item_id"] == item_id), None)
        if not it:
            continue
        rt = next((si["reminder_type"] for si in s["suggestions"] if si["item_id"] == item_id), "progress_check")
        msg = gen_message(item_id, rt, {
            "title": it["title"], "project": "630", "source": it["source"],
            "priority": it["priority_raw"], "handler": ", ".join(it["handler_chain"]),
            "due_date": it.get("due_date"), "remark": it.get("remark"),
            "status": it["normalized_status"],
        })
        owner = it["owner_list"][0] if it["owner_list"] else "unknown"
        wl = contacts.get(owner, {}).get("welink_id", owner) if contacts else owner
        sr = send_welink(item_id=item_id, owner=owner, welink_id=wl,
                        message=msg["message"], reminder_type=rt,
                        confirmation_token=human["confirmation_token"], run_id=run_id,
                        contacts=contacts)
        if sr["status"] == "sent":
            sent += 1
        print(f"  {item_id}: {sr['status']}")
    print(f"  sent: {sent}")

    print("[dry_run] write_decision ...")
    d = write_decision(
        decision_type="brief",
        rationale=f"dry-run: {r['count']} items, {s['count']} suggestions, {sent} sent",
        run_id=run_id,
        action_taken=f"send_welink x{sent}",
    )
    print(f"  decision_id: {d['decision_id']}")

    print("[dry_run] update_context_brief ...")
    b = update_context_brief(
        brief=f"dry-run: {r['count']} items scanned, {s['count']} suggestions, {sent} sent (mock)",
        run_id=run_id,
    )
    print(f"  brief_id: {b['brief_id']}")

    print("\n[dry_run] 完成。Excel mtime 不变。")


def cmd_cron(args: argparse.Namespace) -> None:
    """cron 模式：无人值守，只决策不发送。"""
    cfg = load_config(args.config)

    api_key = cfg["llm"]["api_key"]
    if not api_key:
        print("错误: 未设置 ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    model = args.model or cfg["llm"]["model"]
    max_tokens = cfg["llm"]["max_tokens"]
    max_tokens_per_loop = args.max_tokens or cfg["llm"]["max_tokens_per_loop"]

    print(f"[cron] 启动 · {model} · token 上限 {max_tokens_per_loop}")

    from pm_agent.agent import run_agent

    result = run_agent(
        trigger_reason="cron",
        api_key=api_key,
        base_url=cfg["llm"].get("base_url"),
        model=model,
        max_tokens=max_tokens,
        max_tokens_per_loop=max_tokens_per_loop,
        db_path=cfg["memory"]["db_path"],
        excel_path=cfg["excel"]["path"],
        sheet_name=cfg["excel"]["sheet"],
        contacts=None,
    )

    if not args.quiet:
        print(f"[cron] 完成 · run_id={result['run_id']} · "
              f"tokens={result['total_tokens']} · brief={'ok' if result['brief_written'] else 'miss'}")


def cmd_retrospect(args: argparse.Namespace) -> None:
    """回顾近 N 天决策历史（不调 LLM）。"""
    cfg = load_config()
    db_path = Path(cfg["memory"]["db_path"])
    days = args.days or 7

    if not db_path.exists():
        print("暂无历史数据。")
        return

    from pm_agent.memory.store import Store

    store = Store(db_path)
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    print(f"\n{'='*60}")
    print(f"MobiusPM · 近 {days} 天决策回顾")
    print(f"{'='*60}\n")

    # Decisions
    cur = store._conn.execute(
        "SELECT decision_type, rationale, target_item_id, action_taken, created_at "
        "FROM decision_log WHERE created_at >= ? ORDER BY created_at DESC",
        (cutoff,),
    )
    decisions = cur.fetchall()
    if decisions:
        print(f"## 决策记录 ({len(decisions)} 条)\n")
        for d in decisions:
            print(f"  [{d[4][:19]}] [{d[0]}] {d[2] or '-'}")
            print(f"    理由: {textwrap.shorten(d[1], width=120, placeholder='...')}")
            if d[3]:
                print(f"    动作: {d[3]}")
            print()
    else:
        print("(无决策记录)\n")

    # Briefs
    cur2 = store._conn.execute(
        "SELECT run_id, brief, token_count, created_at FROM context_brief "
        "WHERE created_at >= ? ORDER BY id DESC",
        (cutoff,),
    )
    briefs = cur2.fetchall()
    if briefs:
        print(f"## 上下文摘要 ({len(briefs)} 条)\n")
        for b in briefs:
            print(f"  [{b[3][:19]}] run={b[0]} token={b[2]}")
            print(f"    {textwrap.shorten(b[1], width=200, placeholder='...')}")
            print()

    # Follow-ups
    cur3 = store._conn.execute(
        "SELECT item_id, owner, send_status, created_at FROM follow_up_log "
        "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 50",
        (cutoff,),
    )
    follow_ups = cur3.fetchall()
    if follow_ups:
        print(f"## 发送记录 ({len(follow_ups)} 条)\n")
        for f in follow_ups:
            print(f"  [{f[3][:19]}] {f[0]} → {f[1]} ({f[2]})")

    store.close()
    print(f"\n{'='*60}\n")


def cmd_daemon(args: argparse.Namespace) -> None:
    """daemon 模式：单进程定时循环，自动执行 cron + 等待 PM 唤醒。"""
    import signal
    import time
    from datetime import datetime

    import schedule

    cfg = load_config(args.config)

    api_key = cfg["llm"]["api_key"]
    if not api_key:
        print("错误: 未设置 ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    model = args.model or cfg["llm"]["model"]
    max_tokens = cfg["llm"]["max_tokens"]
    max_tokens_per_loop = args.max_tokens or cfg["llm"]["max_tokens_per_loop"]

    daemon_cfg = cfg.get("daemon", {})
    cron_at = args.cron_at or daemon_cfg.get("cron_at", "09:00")

    print("=" * 60)
    print("MobiusPM Agent · daemon 模式")
    print(f"模型: {model}  |  定时: 每天 {cron_at}")
    print(f"按 Ctrl+C 退出  |  输入 wake 后回车立即触发")
    print("=" * 60)

    run_count = {"value": 0}
    shutdown = {"flag": False}

    def do_cron():
        from pm_agent.agent import run_agent

        run_count["value"] += 1
        print(f"\n[{datetime.now():%H:%M:%S}] cron #{run_count['value']} 开始 ...")
        try:
            result = run_agent(
                trigger_reason="cron",
                api_key=api_key,
                base_url=cfg["llm"].get("base_url"),
                model=model,
                max_tokens=max_tokens,
                max_tokens_per_loop=max_tokens_per_loop,
                db_path=cfg["memory"]["db_path"],
                excel_path=cfg["excel"]["path"],
                sheet_name=cfg["excel"]["sheet"],
                contacts=None,
            )
            print(f"[{datetime.now():%H:%M:%S}] cron 完成 · run_id={result['run_id']} · "
                  f"tokens={result['total_tokens']} · brief={'ok' if result['brief_written'] else 'miss'}")
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] cron 失败: {e}", file=sys.stderr)

    def do_wake():
        from pm_agent.agent import run_agent

        contacts = None
        contacts_path = Path("config/contacts.yaml")
        if contacts_path.exists():
            from pm_agent.tools.contacts import load_contacts as lc
            contacts = lc(contacts_path)

        print(f"\n[{datetime.now():%H:%M:%S}] wake 开始 ...")
        try:
            result = run_agent(
                trigger_reason="wake",
                api_key=api_key,
                base_url=cfg["llm"].get("base_url"),
                model=model,
                max_tokens=max_tokens,
                max_tokens_per_loop=max_tokens_per_loop,
                db_path=cfg["memory"]["db_path"],
                excel_path=cfg["excel"]["path"],
                sheet_name=cfg["excel"]["sheet"],
                contacts=contacts,
            )
            print(f"[{datetime.now():%H:%M:%S}] wake 完成 · run_id={result['run_id']} · "
                  f"tokens={result['total_tokens']} · brief={'ok' if result['brief_written'] else 'miss'}")
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] wake 失败: {e}", file=sys.stderr)

    def on_signal(sig, frame):
        print(f"\n[{datetime.now():%H:%M:%S}] 收到退出信号，正在安全停止 ...")
        shutdown["flag"] = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # 注册定时任务
    schedule.every().day.at(cron_at).do(do_cron)

    # 首次启动立即跑一次
    if not args.no_initial:
        do_cron()

    print(f"\n下次定时触发: {cron_at}  |  输入 wake 手动触发  |  Ctrl+C 退出\n")

    # 主循环
    import threading

    def stdin_reader():
        while not shutdown["flag"]:
            try:
                line = input()
                if line.strip().lower() == "wake":
                    print("  → 手动触发 wake ...")
                    do_wake()
                elif line.strip().lower() == "cron":
                    print("  → 手动触发 cron ...")
                    do_cron()
                elif line.strip().lower() in ("q", "quit", "exit"):
                    shutdown["flag"] = True
                    break
                elif line.strip():
                    print(f"  未知命令: {line.strip()}（可用: wake / cron / quit）")
            except EOFError:
                break

    reader = threading.Thread(target=stdin_reader, daemon=True)
    reader.start()

    try:
        while not shutdown["flag"]:
            schedule.run_pending()
            time.sleep(1)
    finally:
        print(f"[{datetime.now():%H:%M:%S}] daemon 已停止，共执行 {run_count['value']} 次 cron。")
        # 尝试停止 stdin reader
        import os as _os
        try:
            _os.kill(_os.getpid(), signal.SIGINT)
        except Exception:
            pass


def cmd_audit(args: argparse.Namespace) -> None:
    """audit 模式：审视跟踪体系质量（覆盖度、数据质量、规则合理性）"""
    cfg = load_config(args.config)

    api_key = cfg["llm"]["api_key"]
    if not api_key:
        print("错误: 未设置 ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    model = args.model or cfg["llm"]["model"]
    max_tokens = cfg["llm"]["max_tokens"]
    max_tokens_per_loop = args.max_tokens or cfg["llm"]["max_tokens_per_loop"]

    # 审计专用 prompt
    audit_prompt_path = Path(__file__).resolve().parent / "prompts" / "audit.md"
    audit_prompt = audit_prompt_path.read_text(encoding="utf-8") if audit_prompt_path.exists() else None

    print("=" * 60)
    print("MobiusPM Agent · audit 模式")
    print(f"模型: {model}  |  审视跟踪体系")
    print("=" * 60)

    from pm_agent.agent import run_agent

    result = run_agent(
        trigger_reason="audit",
        system_prompt=audit_prompt,
        api_key=api_key,
        base_url=cfg["llm"].get("base_url"),
        model=model,
        max_tokens=max_tokens,
        max_tokens_per_loop=max_tokens_per_loop,
        db_path=cfg["memory"]["db_path"],
        excel_path=cfg["excel"]["path"],
        sheet_name=cfg["excel"]["sheet"],
        contacts=None,
    )

    print(f"\nrun_id: {result['run_id']}")
    print(f"tokens: {result['total_tokens']} ({result['iterations']} iterations)")
    print(f"报告: {'已生成' if result['brief_written'] else '未生成'}")
    print("查看详细报告: state/reports/")


def main() -> None:
    parser = argparse.ArgumentParser(prog="pm_agent")
    sub = parser.add_subparsers(dest="command")

    # wake
    p_wake = sub.add_parser("wake", help="唤醒 agent（PM 在场，可对话确认 + mock 发送）")
    p_wake.add_argument("--config", default="config/pm-agent.yaml")
    p_wake.add_argument("--model", default=None)
    p_wake.add_argument("--base-url", default=None, help="自定义 LLM endpoint（代理/兼容 API）")
    p_wake.add_argument("--max-tokens", type=int, default=None, help="单次 LLM 调用输出上限，默认按配置")
    p_wake.add_argument("--budget", type=int, default=None, help="全 loop 总 token 预算，默认按配置")
    p_wake.add_argument("--dry-run", action="store_true", help="不调 LLM，直接联级工具验证")

    # cron
    p_cron = sub.add_parser("cron", help="cron 模式（无人值守，只决策不发送）")
    p_cron.add_argument("--config", default="config/pm-agent.yaml")
    p_cron.add_argument("--model", default=None)
    p_cron.add_argument("--max-tokens", type=int, default=None)
    p_cron.add_argument("--quiet", action="store_true", help="精简输出")

    # retrospect
    p_retro = sub.add_parser("retrospect", help="回顾近 N 天决策历史（不调 LLM）")
    p_retro.add_argument("--days", type=int, default=7)
    p_retro.add_argument("--config", default="config/pm-agent.yaml")

    # daemon
    p_daemon = sub.add_parser("daemon", help="守护进程模式（定时 cron + 手动 wake，无需 OS 调度器）")
    p_daemon.add_argument("--config", default="config/pm-agent.yaml")
    p_daemon.add_argument("--model", default=None)
    p_daemon.add_argument("--max-tokens", type=int, default=None)
    p_daemon.add_argument("--cron-at", default=None, help="每天定时触发时间，默认 09:00")
    p_daemon.add_argument("--no-initial", action="store_true", help="启动时不立即运行 cron")

    # audit
    p_audit = sub.add_parser("audit", help="审计跟踪体系（覆盖度、数据质量、规则合理性）")
    p_audit.add_argument("--config", default="config/pm-agent.yaml")
    p_audit.add_argument("--model", default=None)
    p_audit.add_argument("--max-tokens", type=int, default=None)

    # debug
    p_debug = sub.add_parser("debug", help="直接调工具，绕过 agent loop")
    p_debug.add_argument("--tool", required=True,
                        choices=["read_excel", "query_state", "query_history", "safety"])
    p_debug.add_argument("--item-id", default=None)
    p_debug.add_argument("--max-records", type=int, default=10)
    p_debug.add_argument("--subtool", default=None)
    p_debug.add_argument("--welink-id", default=None)
    p_debug.add_argument("--reminder-type", default=None)
    p_debug.add_argument("--run-id", default=None)

    args = parser.parse_args()

    if args.command == "wake":
        cmd_wake(args)
    elif args.command == "cron":
        cmd_cron(args)
    elif args.command == "retrospect":
        cmd_retrospect(args)
    elif args.command == "daemon":
        cmd_daemon(args)
    elif args.command == "audit":
        cmd_audit(args)
    elif args.command == "debug":
        cmd_debug(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
