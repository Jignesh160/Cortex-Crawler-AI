"""Configuration with self-contained defaults.

The library works with ZERO config files (important when pulled into a chatbot):
built-in DEFAULTS are used unless overridden by:
  1. DEFAULTS (this file)
  2. a YAML file: explicit path arg, else $CORTEX_CONFIG, else ./config/settings.yaml
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Built-in defaults so the crawler runs anywhere out of the box.
DEFAULTS: dict[str, Any] = {
    "crawl": {
        "user_agent": "CortexCrawlerBot/0.1 (+https://example.com/bot)",
        # Default false: this tool crawls first-party (own) sites. Set true if you
        # ever crawl third-party sites you don't control.
        "obey_robots": False,
        "rate_limit_per_domain": 1.0,
        "timeout": 20.0,
        "max_pages": 50,
        "max_depth": 2,
        "same_domain_only": True,
        "max_retries": 3,
        "dynamic_fallback": True,   # auto-render JS pages when static yield is thin
        "dynamic_min_chars": 200,   # static extraction below this -> retry via browser
        "dynamic_wait_ms": 2000,    # settle time after load
        "include": [],              # if set, only URLs matching a glob are crawled
        "exclude": [                # URLs matching any glob are never fetched/emitted
            "*/cookies*", "*/legalNotice", "*/legal-notice", "*/privacy*",
            "*/request-for-quote*", "*/terms*", "*/login*",
        ],
    },
    "extract": {"min_text_chars": 200},
    "images": {
        "enabled": True, "min_width": 100, "min_height": 100,
        "max_aspect_ratio": 10.0, "min_bytes": 2048,
        "allowed_types": ["jpeg", "jpg", "png", "webp", "gif"],
        "phash_hamming_threshold": 6,
    },
    "dedup": {"text_near_dup": True, "minhash_threshold": 0.85},
    "output": {"root": "knowledge", "image_base_url": ""},
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Config:
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def crawl(self) -> dict[str, Any]:
        return self.raw.get("crawl", {})

    @property
    def extract(self) -> dict[str, Any]:
        return self.raw.get("extract", {})

    @property
    def images(self) -> dict[str, Any]:
        return self.raw.get("images", {})

    @property
    def dedup(self) -> dict[str, Any]:
        return self.raw.get("dedup", {})

    @property
    def output(self) -> dict[str, Any]:
        return self.raw.get("output", {})


def _resolve_path(path: str | Path | None) -> Path | None:
    if path:
        return Path(path)
    env = os.getenv("CORTEX_CONFIG")
    if env:
        return Path(env)
    cwd_cfg = Path.cwd() / "config" / "settings.yaml"
    return cwd_cfg if cwd_cfg.exists() else None


def load_config(path: str | Path | None = None) -> Config:
    data = copy.deepcopy(DEFAULTS)
    p = _resolve_path(path)
    if p is not None:
        if not p.exists():
            raise FileNotFoundError(f"config file not found: {p}")
        with open(p, "r", encoding="utf-8") as fh:
            file_cfg = yaml.safe_load(fh) or {}
        data = _deep_merge(data, file_cfg)
    return Config(raw=data)
