from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """NFKC + 空白压缩 + 中文标点统一。不改语义。"""
    # 1. Unicode NFKC 归一化
    s = unicodedata.normalize("NFKC", text)
    # 2. 空白压缩（连续空白 → 单空格，首尾去空格）
    s = re.sub(r"\s+", " ", s).strip()
    # 3. 中文标点统一（全角逗号、顿号 → 半角逗号）
    s = s.replace("，", ",").replace("、", ",")
    return s


def make_item_id(source: str, title: str) -> str:
    """sha1(来源 + '::' + normalize(原文))[:12]"""
    import hashlib

    key = f"{source}::{normalize(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
