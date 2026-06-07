"""Configuration with self-contained defaults.

The library works with ZERO config files (important when pulled into a chatbot):
built-in DEFAULTS are used unless overridden by, in increasing precedence:
  1. DEFAULTS (this file)
  2. a YAML file: explicit path arg, else $CORTEX_CONFIG, else ./config/settings.yaml
  3. environment variables for deploy-specific/secret values (region, buckets, ...)
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Built-in production-safe defaults. Local backends so it runs anywhere out of the box.
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
    "rag": {
        "chunk_target_tokens": 500,
        "semantic_dedup_threshold": 0.97,
        "embedder": {"backend": "local", "dim": 512},
        "store": {"backend": "local", "path": "index/local_store"},
        "answer": {"backend": "local"},
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_overrides(cfg: dict) -> dict:
    """Map well-known env vars onto config (deploy-specific + secrets)."""
    cfg = copy.deepcopy(cfg)
    rag = cfg.setdefault("rag", {})
    region = os.getenv("AWS_REGION") or os.getenv("CORTEX_AWS_REGION")
    if region:
        for sub in ("embedder", "store", "answer"):
            rag.setdefault(sub, {})["region"] = region
    if os.getenv("CORTEX_EMBEDDER_BACKEND"):
        rag.setdefault("embedder", {})["backend"] = os.environ["CORTEX_EMBEDDER_BACKEND"]
    if os.getenv("CORTEX_STORE_BACKEND"):
        rag.setdefault("store", {})["backend"] = os.environ["CORTEX_STORE_BACKEND"]
    if os.getenv("CORTEX_ANSWER_BACKEND"):
        rag.setdefault("answer", {})["backend"] = os.environ["CORTEX_ANSWER_BACKEND"]
    if os.getenv("CORTEX_VECTOR_BUCKET"):
        rag.setdefault("store", {})["bucket"] = os.environ["CORTEX_VECTOR_BUCKET"]
    if os.getenv("CORTEX_VECTOR_INDEX"):
        rag.setdefault("store", {})["index"] = os.environ["CORTEX_VECTOR_INDEX"]
    if os.getenv("CORTEX_IMAGE_BASE_URL"):
        cfg.setdefault("output", {})["image_base_url"] = os.environ["CORTEX_IMAGE_BASE_URL"]
    return cfg


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

    @property
    def rag(self) -> dict[str, Any]:
        return self.raw.get("rag", {})


def _resolve_path(path: str | Path | None) -> Path | None:
    if path:
        return Path(path)
    env = os.getenv("CORTEX_CONFIG")
    if env:
        return Path(env)
    cwd_cfg = Path.cwd() / "config" / "settings.yaml"
    return cwd_cfg if cwd_cfg.exists() else None


def _maybe_load_dotenv() -> None:
    """Best-effort: load a local .env into the environment if python-dotenv is
    installed. No-op otherwise (env vars set directly still work)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _reconcile_dims(cfg: dict) -> dict:
    """Keep embedder dim and vector-store dim consistent. Titan = 1024 by default."""
    rag = cfg.setdefault("rag", {})
    emb = rag.setdefault("embedder", {})
    store = rag.setdefault("store", {})
    if emb.get("backend") == "bedrock" and emb.get("dim", 512) == 512:
        emb["dim"] = 1024  # Titan multimodal default
    store["dim"] = emb.get("dim", 1024 if emb.get("backend") == "bedrock" else 512)
    return cfg


def load_config(path: str | Path | None = None) -> Config:
    _maybe_load_dotenv()
    data = copy.deepcopy(DEFAULTS)
    p = _resolve_path(path)
    if p is not None:
        if not p.exists():
            raise FileNotFoundError(f"config file not found: {p}")
        with open(p, "r", encoding="utf-8") as fh:
            file_cfg = yaml.safe_load(fh) or {}
        data = _deep_merge(data, file_cfg)
    data = _env_overrides(data)
    data = _reconcile_dims(data)
    return Config(raw=data)
