"""MVP 场景端到端测试 — 验证 python -m pm_agent wake --dry-run 全流程"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from pm_agent.config import load_config
from pm_agent.tools.excel import read_excel
from pm_agent.tools.rules import query_rule_suggestions
from pm_agent.tools.messages import gen_message
from pm_agent.tools.human import ask_human
from pm_agent.tools.notifier import send_welink, clear_confirmation_token
from pm_agent.tools.state import write_decision, update_context_brief
from pm_agent.tools.contacts import load_contacts

FAILURES: list[str] = []


def check(desc: str, ok: bool, detail: str = "") -> None:
    status = "✓" if ok else "✗"
    line = f"  {status} {desc}"
    if not ok and detail:
        line += f"  → {detail}"
    print(line)
    if not ok:
        FAILURES.append(desc)


def test_read_excel(cfg: dict) -> dict:
    print("\n[1/7] read_excel ...")
    r = read_excel(Path(cfg["excel"]["path"]), cfg["excel"]["sheet"])
    check("返回 dict", isinstance(r, dict))
    check("含 items 键", "items" in r)
    check("count > 0", r.get("count", 0) > 0, f"count={r.get('count')}")
    check("items 是 list", isinstance(r.get("items"), list))
    if r["items"]:
        it = r["items"][0]
        check("item 含 item_id", "item_id" in it, str(it.get("item_id")))
        check("item 含 normalized_status", "normalized_status" in it)
    return r


def test_rules(excel_result: dict) -> dict:
    print("\n[2/7] query_rule_suggestions ...")
    s = query_rule_suggestions(excel_result["items"])
    check("返回 dict", isinstance(s, dict))
    check("含 suggestions", "suggestions" in s)
    check("含 summary", "summary" in s)
    check("suggestions 是 list", isinstance(s.get("suggestions"), list))
    if s["suggestions"]:
        sg = s["suggestions"][0]
        check("suggestion 含 rule_id", "rule_id" in sg)
        check("suggestion 含 severity", "severity" in sg)
    return s


def test_ask_human(suggestions: dict) -> dict:
    print("\n[3/7] ask_human (auto_yes) ...")
    candidates = suggestions["suggestions"][:5]
    h = ask_human(candidates, run_id="mvp_test", auto_yes=True)
    check("返回 dict", isinstance(h, dict))
    check("含 confirmation_token", bool(h.get("confirmation_token")))
    check("含 confirmed_item_ids", isinstance(h.get("confirmed_item_ids"), list))
    return h


def test_gen_message(excel_result: dict) -> dict | None:
    print("\n[4/7] gen_message ...")
    items = excel_result["items"]
    if not items:
        print("  - 无 items，跳过")
        return None
    it = items[0]
    msg = gen_message(
        it["item_id"], "progress_check",
        {
            "title": it["title"], "project": "630", "source": it["source"],
            "priority": it["priority_raw"], "handler": ", ".join(it["handler_chain"]),
            "due_date": it.get("due_date"), "remark": it.get("remark"),
            "status": it["normalized_status"],
        },
    )
    check("返回 dict", isinstance(msg, dict))
    check("含 message 文本", bool(msg.get("message")), str(msg.get("message", "")[:60]))
    check("message 非空", len(msg.get("message", "")) > 20)
    return msg


def test_send_welink(
    excel_result: dict, human_result: dict, msg_result: dict | None, contacts: dict | None
) -> None:
    print("\n[5/7] send_welink (mock) ...")
    items = excel_result["items"]
    confirmed_ids = human_result["confirmed_item_ids"]
    if not confirmed_ids or not items:
        print("  - 无确认项，跳过")
        return

    item_id = confirmed_ids[0]
    it = next((i for i in items if i["item_id"] == item_id), items[0])
    owner = it["owner_list"][0] if it["owner_list"] else "unknown"
    wl = contacts.get(owner, {}).get("welink_id", owner) if contacts else owner
    message = msg_result["message"] if msg_result else "test message"

    # ask_human 用 mvp_test 存了 token，send_welink 必须用同一个 run_id
    test_run_id = "mvp_test"

    # 第一次发送
    r1 = send_welink(
        item_id=item_id, owner=owner, welink_id=wl,
        message=message, reminder_type="progress_check",
        confirmation_token=human_result["confirmation_token"],
        run_id=test_run_id,
    )
    check("send_welink 成功", r1.get("status") == "sent", str(r1))

    # 幂等检查：同 item_id + 同类型再次发送应被 block
    # 先重新存 token（同一 run_id 被第一次发送消耗后需刷新）
    from pm_agent.tools.notifier import store_confirmation_token
    store_confirmation_token(test_run_id, human_result["confirmation_token"])
    r2 = send_welink(
        item_id=item_id, owner=owner, welink_id=wl,
        message=message, reminder_type="progress_check",
        confirmation_token=human_result["confirmation_token"],
        run_id=test_run_id,
    )
    check("幂等去重生效", r2.get("status") == "blocked" and r2.get("reason") == "dedupe", str(r2))

    # 清理
    clear_confirmation_token(test_run_id)


def test_write_decision(excel_result: dict) -> dict:
    print("\n[6/7] write_decision ...")
    d = write_decision(
        decision_type="brief",
        rationale=f"MVP 测试：读取 {excel_result['count']} 条事项，验证全流程",
        run_id="mvp_test",
        action_taken="send_welink x1 (mock)",
    )
    check("返回 dict", isinstance(d, dict))
    check("status=ok", d.get("status") == "ok")
    check("含 decision_id", bool(d.get("decision_id")))
    return d


def test_update_brief(excel_result: dict) -> dict:
    print("\n[7/7] update_context_brief ...")
    b = update_context_brief(
        brief=f"MVP 测试：{excel_result['count']} 条事项扫描完成，已 mock 发送 1 条",
        run_id="mvp_test",
    )
    check("返回 dict", isinstance(b, dict))
    check("status=ok", b.get("status") == "ok")
    return b


def main() -> int:
    print("=" * 60)
    print("MobiusPM · MVP 场景端到端测试")
    print("=" * 60)

    cfg = load_config()

    # 前置：contacts
    contacts = None
    contacts_path = Path("config/contacts.yaml")
    if contacts_path.exists():
        contacts = load_contacts(contacts_path)
        print(f"\n[前置] 加载 {len(contacts)} 个联系人")
    else:
        print("\n[前置] 无 contacts.yaml，跳过白名单检查")

    # 核心流程
    r = test_read_excel(cfg)
    s = test_rules(r)
    h = test_ask_human(s)
    m = test_gen_message(r)
    test_send_welink(r, h, m, contacts)
    test_write_decision(r)
    test_update_brief(r)

    # 汇总
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"结果: {len(FAILURES)} 项失败")
        for f in FAILURES:
            print(f"  ✗ {f}")
    else:
        print("结果: 全部通过 ✓")
    print("=" * 60)

    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
