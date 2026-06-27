"""CLI 入口：python -m pm_agent"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def _load_config() -> dict:
    cfg_path = Path("config/pm-agent.yaml")
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def cmd_debug(args: argparse.Namespace) -> None:
    cfg = _load_config()
    excel_path = Path(cfg.get("excel", {}).get("path", "source/项目630流水线排期计划.xlsx"))
    sheet_name = cfg.get("excel", {}).get("sheet", "630攻关问题清单")
    from pm_agent.memory.store import DEFAULT_DB_PATH

    db_path = Path(cfg.get("memory", {}).get("db_path", DEFAULT_DB_PATH))

    if args.tool == "read_excel":
        from pm_agent.tools.excel import read_excel

        result = read_excel(excel_path, sheet_name)
        # 失联检测：与 SQLite 比对
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

    elif args.tool == "safety":
        from pm_agent.tools.safety import check_rate_limit, check_run_limit, dedupe_key

        if args.subtool == "dedupe_key":
            result = {"key": dedupe_key(args.item_id, args.reminder_type)}
        elif args.subtool == "check_rate_limit":
            result = check_rate_limit(args.welink_id, db_path=db_path)
        elif args.subtool == "check_run_limit":
            result = check_run_limit(args.run_id, db_path=db_path)
        else:
            print(f"Unknown subtool: {args.subtool}", file=sys.stderr)
            sys.exit(1)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    else:
        print(f"Unknown tool: {args.tool}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pm_agent")
    sub = parser.add_subparsers(dest="command")

    p_debug = sub.add_parser("debug", help="直接调工具，绕过 agent loop")
    p_debug.add_argument("--tool", required=True, choices=["read_excel", "query_state", "safety"])
    p_debug.add_argument("--item-id", default=None)
    p_debug.add_argument("--subtool", default=None)
    p_debug.add_argument("--welink-id", default=None)
    p_debug.add_argument("--reminder-type", default=None)
    p_debug.add_argument("--run-id", default=None)

    args = parser.parse_args()
    if args.command == "debug":
        cmd_debug(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
