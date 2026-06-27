"""统一配置加载 — env var + YAML 合并"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_DEFAULT_CONFIG = Path("config/pm-agent.yaml")


def load_config(path: str | Path = _DEFAULT_CONFIG) -> dict:
    cfg: dict = {}
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # API key: 优先 env var
    if not cfg.get("anthropic", {}).get("api_key"):
        cfg.setdefault("anthropic", {})["api_key"] = os.environ.get(
            "ANTHROPIC_API_KEY", ""
        )

    # 默认值填充
    cfg.setdefault("anthropic", {}).setdefault("model", "claude-opus-4-7")
    cfg.setdefault("anthropic", {}).setdefault("max_tokens", 4096)
    cfg.setdefault("anthropic", {}).setdefault("max_tokens_per_loop", 50000)
    cfg.setdefault("excel", {}).setdefault("path", "source/项目630流水线排期计划.xlsx")
    cfg.setdefault("excel", {}).setdefault("sheet", "630攻关问题清单")
    cfg.setdefault("memory", {}).setdefault("db_path", "state/pm-agent.db")
    cfg.setdefault("memory", {}).setdefault("lookback_days", 14)
    cfg.setdefault("memory", {}).setdefault("recent_decision_limit", 20)
    cfg.setdefault("memory", {}).setdefault("max_briefs", 30)
    cfg.setdefault("notifier", {}).setdefault("mode", "mock")
    cfg.setdefault("notifier", {}).setdefault("welink", {}).setdefault("cli_path", "welink")
    cfg.setdefault("notifier", {}).setdefault("welink", {}).setdefault("timeout", 30)
    cfg.setdefault("notifier", {}).setdefault("welink", {}).setdefault("retry_count", 1)
    cfg.setdefault("reminder", {}).setdefault("max_per_owner_per_day", 5)
    cfg.setdefault("reminder", {}).setdefault("max_per_run", 50)
    cfg.setdefault("mode", "wake")

    return cfg
