"""Heading-aware markdown chunking (ARCHITECTURE_FINAL.md §0 — the #1 quality lever).

Parses a knowledge/*.md file (YAML front-matter + body), splits on markdown headings,
and packs sections into ~target-token chunks WITHOUT crossing heading boundaries where
possible. Every chunk carries provenance (source_url, section_path) for citations.

Images: the per-page image references in the body become their own "image chunks" so
they live in the same index as text (matches the multimodal design).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Pure, stateless text-similarity utility (no crawler state) — shared across layers.
from ..engine.dedup import NearDupFilter

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_IMG = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)")


@dataclass
class Chunk:
    chunk_id: str
    source_url: str
    title: str
    section_path: str
    text: str
    heading: str = ""               # leaf section heading (the chunk's topic)
    modality: str = "text"          # text | image
    image_url: str = ""
    image_id: str = ""
    content_hash: str = ""
    meta: dict = field(default_factory=dict)


def _approx_tokens(s: str) -> int:
    # Cheap heuristic: ~1 token per 4 chars. Good enough for sizing.
    return max(1, len(s) // 4)


def parse_markdown(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        front = yaml.safe_load(fm) or {}
        return front, body.strip()
    return {}, raw.strip()


def _iter_sections(body: str):
    """Yield (heading, section_path, text) segments split on heading boundaries.

    `heading` is the nearest (leaf) heading; `section_path` is the full
    breadcrumb (e.g. "Design > Premium Interior"). Content before the first
    heading is yielded with an empty heading/path (the page preamble).
    """
    stack: list[str] = []
    buf: list[str] = []
    cur_heading = ""
    cur_path = ""

    def flush():
        text = "\n".join(buf).strip()
        return (cur_heading, cur_path, text) if text else None

    for line in body.splitlines():
        m = _HEADING.match(line)
        if m:
            seg = flush()
            if seg:
                yield seg
            buf = []
            level = len(m.group(1))
            cur_heading = m.group(2).strip()
            stack[:] = stack[: level - 1]
            stack.append(cur_heading)
            cur_path = " > ".join(stack)
        else:
            buf.append(line)
    seg = flush()
    if seg:
        yield seg


def chunk_file(path: Path, target_tokens: int = 500, overlap_tokens: int = 60) -> list[Chunk]:
    front, body = parse_markdown(path)
    source_url = front.get("source_url", "")
    title = front.get("title", path.stem)
    base_hash = front.get("content_hash", "")

    chunks: list[Chunk] = []
    n = 0
    # Intra-page near-dup filter: drop a chunk that repeats an earlier block on the
    # SAME page (e.g. specs shown both as flattened text and as a table).
    near_dup = NearDupFilter(threshold=0.9)

    # --- text chunks: split on heading boundaries FIRST (one section = one topic),
    #     then size-cap within a section that's too big (windowed with overlap) ---
    def _emit(heading: str, section_path: str, body_text: str) -> None:
        nonlocal n
        if near_dup.is_duplicate(body_text):
            return
        n += 1
        # Fold the heading into the chunk text so the embedding captures the topic.
        text = f"{heading}\n\n{body_text}" if heading else body_text
        chunks.append(Chunk(
            chunk_id=f"{base_hash[:12]}-{n}",
            source_url=source_url, title=title,
            section_path=section_path or title, text=text,
            heading=heading or title, content_hash=base_hash,
        ))

    for heading, section_path, text in _iter_sections(body):
        # Skip the auto-generated image appendix as text; images handled separately.
        if section_path.endswith("Images") and _IMG.search(text):
            continue
        if not text.strip():
            continue
        if _approx_tokens(text) <= target_tokens:
            _emit(heading, section_path, text)
        else:
            words = text.split()
            step = max(1, (target_tokens - overlap_tokens) * 4 // 5)  # words/chunk approx
            size = max(1, target_tokens * 4 // 5)
            for i in range(0, len(words), step):
                piece = " ".join(words[i:i + size]).strip()
                if piece:
                    _emit(heading, section_path, piece)

    # --- image chunks: one per referenced image, carrying alt as searchable text ---
    seen_img: set[str] = set()
    for m in _IMG.finditer(body):
        url = m.group("url")
        if url in seen_img:
            continue
        seen_img.add(url)
        alt = m.group("alt").strip()
        image_id = Path(url).stem
        n += 1
        chunks.append(Chunk(
            chunk_id=f"{base_hash[:12]}-img-{n}",
            source_url=source_url, title=title,
            section_path=f"{title} > image", text=alt or title,
            modality="image", image_url=url, image_id=image_id,
            content_hash=base_hash,
        ))

    return chunks


def chunk_knowledge(root: Path, target_tokens: int = 500) -> list[Chunk]:
    out: list[Chunk] = []
    for md in sorted(root.rglob("*.md")):
        out.extend(chunk_file(md, target_tokens=target_tokens))
    return out
