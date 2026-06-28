from __future__ import annotations

import hashlib
import re
import unicodedata


def normalize(text: str) -> str:
    """NFKC + 空白压缩 + 中文标点统一。不改语义。"""
    s = unicodedata.normalize("NFKC", text)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("，", ",").replace("、", ",")
    return s


def make_item_id(source: str, title: str) -> str:
    """sha1(来源 + '::' + normalize(原文))[:12]"""
    key = f"{source}::{normalize(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
