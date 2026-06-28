"""统一配置加载 — env var + YAML 合并，业界标准 llm: 块"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_DEFAULT_CONFIG = Path("config/pm-agent.yaml")

# 默认值定义（只维护一处）
_DEFAULTS = {
    "llm": {
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": None,  # 自定义 endpoint（代理/兼容 API），None=用官方默认
        "max_tokens": 4096,
        "max_tokens_per_loop": 50000,
        "temperature": 0.3,
    },
    "excel": {"path": "source/项目630流水线排期计划.xlsx", "sheet": "630攻关问题清单"},
    "memory": {"db_path": "state/pm-agent.db", "lookback_days": 14, "recent_decision_limit": 20, "max_briefs": 30},
    "notifier": {"mode": "mock", "welink": {"cli_path": "welink", "timeout": 30, "retry_count": 1}},
    "reminder": {"max_per_owner_per_day": 5, "max_per_run": 50},
    "daemon": {"cron_interval_minutes": 60, "cron_at": "09:00"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: str | Path = _DEFAULT_CONFIG) -> dict:
    p = Path(path)
    cfg: dict = _deep_merge(
        {k: v.copy() if isinstance(v, dict) else v for k, v in _DEFAULTS.items()},
        yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {},
    )

    # API key: 从 env var 读取（key 名由 llm.api_key_env 指定）
    api_key_env = cfg["llm"].get("api_key_env", "ANTHROPIC_API_KEY")
    cfg["llm"]["api_key"] = os.environ.get(api_key_env, "")

    return cfg
