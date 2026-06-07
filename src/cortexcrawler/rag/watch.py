"""Watch the knowledge/ folder and keep chunks.jsonl in sync with the .md files.

Whenever a markdown file is added, edited, or removed, the chunks export is
regenerated. Dependency-free (mtime polling) so it runs anywhere, including
Windows. Use via `cortex-watch`.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..log import get_logger
from .export import export_chunks

_log = get_logger("watch")


def snapshot(root: str | Path) -> dict[str, float]:
    """Map of every .md file -> its modification time (detects add/edit/remove)."""
    return {str(p): p.stat().st_mtime for p in Path(root).rglob("*.md")}


def watch_and_export(knowledge_root: str, out_path: str, interval: float = 2.0,
                     target_tokens: int = 500, run_once: bool = False) -> dict:
    """Export once immediately, then re-export on any .md change.

    run_once=True does a single export and returns (used by tests / one-shot runs).
    Otherwise loops until interrupted. Returns the last export stats.
    """
    last: dict[str, float] | None = None
    stats: dict = {}
    while True:
        snap = snapshot(knowledge_root)
        if snap != last:
            stats = export_chunks(knowledge_root, out_path, target_tokens=target_tokens)
            _log.info("chunks updated: %d records -> %s", stats["total"], stats["path"])
            last = snap
        if run_once:
            return stats
        time.sleep(interval)
