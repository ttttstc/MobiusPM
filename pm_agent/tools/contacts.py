"""联系人映射加载 — contacts.yaml"""
from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULT_PATH = Path("config/contacts.yaml")


def load_contacts(
    path: str | Path = _DEFAULT_PATH,
) -> dict[str, dict]:
    """
    加载 contacts.yaml，返回 {姓名: {welink_id, enabled, aliases}} 映射。

    同时构建 aliases → 正名的反向索引，调用方通过 resolve_contact
    可以处理 "李坤(gitcode)" → "李坤" 这类脏数据。
    """
    p = Path(path)
    if not p.exists():
        return {}

    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    result: dict[str, dict] = {}
    for entry in raw.get("contacts", []):
        name = entry.get("name", "").strip()
        if not name:
            continue
        result[name] = {
            "welink_id": entry.get("welink_id", "").strip(),
            "enabled": entry.get("enabled", True),
            "aliases": entry.get("aliases", []),
        }
    return result


def resolve_contact(
    owner_name: str,
    contacts: dict[str, dict],
) -> dict | None:
    """
    解析联系人：先精确匹配，再查 aliases。

    返回 {"name": str, "welink_id": str, "enabled": bool} 或 None。
    """
    name = owner_name.strip()
    # 精确匹配
    if name in contacts:
        c = contacts[name]
        return {"name": name, "welink_id": c["welink_id"], "enabled": c["enabled"]}
    # aliases 匹配
    for cname, cdata in contacts.items():
        if name in cdata.get("aliases", []):
            return {"name": cname, "welink_id": cdata["welink_id"], "enabled": cdata["enabled"]}
    return None
