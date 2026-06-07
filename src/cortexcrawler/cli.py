"""Console entry points: `cortex-crawl`, `cortex-index`, `cortex-ask`.

Thin wrappers over the KnowledgeBase public API. App-level logging is configured
here (library code never configures handlers itself).
"""
from __future__ import annotations

import argparse
import sys

from .api import KnowledgeBase
from .engine.config import load_config
from .log import setup_logging
from .rag.answer import answer as _answer


def _kb(args) -> KnowledgeBase:
    cfg = load_config(getattr(args, "config", None))
    return KnowledgeBase(config=cfg)


def crawl_cmd(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="cortex-crawl",
                                 description="Crawl a site into knowledge/*.md + images")
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


def index_cmd(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="cortex-index",
                                 description="Build the vector index from knowledge/")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)

    stats = _kb(args).index()
    print(f"[index] chunks={stats['chunks']} text={stats['text']} "
          f"image={stats['image']} semantic_deduped={stats['deduped']} "
          f"upserted={stats['upserted']}")
    return 0


def chunks_cmd(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="cortex-chunks",
                                 description="Export RAG-ready chunks as JSONL from knowledge/")
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default="datasets/chunks.jsonl", help="output JSONL path")
    args = ap.parse_args(argv)

    from .rag.export import export_chunks
    cfg = load_config(args.config)
    stats = export_chunks(
        knowledge_root=cfg.output.get("root", "knowledge"),
        out_path=args.out,
        target_tokens=cfg.rag.get("chunk_target_tokens", 500),
    )
    print(f"[chunks] wrote {stats['total']} records "
          f"(text={stats['text']} image={stats['image']}) -> {stats['path']}")
    return 0


def watch_cmd(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="cortex-watch",
                                 description="Watch knowledge/ and auto-rebuild chunks.jsonl on .md changes")
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default="datasets/chunks.jsonl", help="output JSONL path")
    ap.add_argument("--interval", type=float, default=2.0, help="poll interval (seconds)")
    args = ap.parse_args(argv)

    from .rag.watch import watch_and_export
    cfg = load_config(args.config)
    root = cfg.output.get("root", "knowledge")
    tokens = cfg.rag.get("chunk_target_tokens", 500)
    print(f"[watch] watching '{root}/' -> {args.out} (every {args.interval}s). Ctrl+C to stop.")
    try:
        watch_and_export(root, args.out, interval=args.interval, target_tokens=tokens)
    except KeyboardInterrupt:
        print("\n[watch] stopped.")
    return 0


def ask_cmd(argv: list[str] | None = None) -> int:
    setup_logging("WARNING")  # keep query output clean
    ap = argparse.ArgumentParser(prog="cortex-ask",
                                 description="Query the knowledge base")
    ap.add_argument("query")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--modality", choices=["text", "image"], default=None)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)

    kb = _kb(args)
    hits = kb.search(args.query, top_k=args.top_k, modality=args.modality)
    if not hits:
        print("No results. Run cortex-index first.")
        return 1
    print(_answer(args.query, hits, kb.config.rag.get("answer", {})))
    return 0


if __name__ == "__main__":  # `python -m cortexcrawler.cli crawl ...`
    cmds = {"crawl": crawl_cmd, "index": index_cmd, "ask": ask_cmd,
            "chunks": chunks_cmd, "watch": watch_cmd}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print("usage: python -m cortexcrawler.cli {crawl|index|ask} ...")
        sys.exit(2)
    sys.exit(cmds[sys.argv[1]](sys.argv[2:]))
