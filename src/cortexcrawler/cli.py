"""Console entry point: `cortex-crawl`.

Thin wrapper over the KnowledgeBase public API. App-level logging is configured
here (library code never configures handlers itself).
"""
from __future__ import annotations

import argparse

from .api import KnowledgeBase
from .engine.config import load_config
from .log import setup_logging


def crawl_cmd(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="cortex-crawl",
                                 description="Crawl a site into knowledge/<site>/*.md + images")
    ap.add_argument("seed", help="seed URL")
    ap.add_argument("--config", default=None)
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--max-depth", type=int, default=None)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    if args.max_pages is not None:
        cfg.raw["crawl"]["max_pages"] = args.max_pages
    if args.max_depth is not None:
        cfg.raw["crawl"]["max_depth"] = args.max_depth

    written = KnowledgeBase(config=cfg).crawl(args.seed)
    print(f"\nDone. {len(written)} markdown file(s) written.")
    return 0 if written else 1


if __name__ == "__main__":  # `python -m cortexcrawler.cli <seed>`
    raise SystemExit(crawl_cmd())
