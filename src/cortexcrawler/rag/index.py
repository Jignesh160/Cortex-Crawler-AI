"""Index orchestrator (ARCHITECTURE_FINAL.md §3, §6).

knowledge/*.md  ->  chunk  ->  embed (text + image)  ->  SEMANTIC DEDUP GATE  ->  upsert.

Nothing reaches the store until it passes the gate => the index is clean by
construction. Reads knowledge/ only; never imports engine/.
"""
from __future__ import annotations

from pathlib import Path

from .chunk import Chunk, chunk_knowledge
from .embed import Embedder
from .semantic_dedup import SemanticDedup
from .store import Record, VectorStore


def _image_bytes_for(chunk: Chunk, knowledge_root: Path) -> bytes | None:
    """Resolve a stored image file for an image chunk (local layout)."""
    if chunk.modality != "image" or not chunk.image_url:
        return None
    # body refs are relative ("images/<sha>.jpg"); find under the page's site dir.
    name = Path(chunk.image_url).name
    for p in knowledge_root.rglob(name):
        return p.read_bytes()
    return None


def build_index(
    knowledge_root: str,
    embedder: Embedder,
    store: VectorStore,
    target_tokens: int = 500,
    semantic_threshold: float = 0.97,
) -> dict:
    root = Path(knowledge_root)
    chunks = chunk_knowledge(root, target_tokens=target_tokens)

    gate = SemanticDedup(threshold=semantic_threshold)
    records: list[Record] = []
    stats = {"chunks": len(chunks), "text": 0, "image": 0, "deduped": 0}

    for ch in chunks:
        if ch.modality == "image":
            img = _image_bytes_for(ch, root)
            vec = embedder.embed_image(img, alt=ch.text) if img is not None \
                else embedder.embed_text(ch.text)
        else:
            vec = embedder.embed_text(ch.text)

        if gate.is_duplicate(vec):
            stats["deduped"] += 1
            continue

        records.append(Record(
            id=ch.chunk_id,
            vector=vec,
            metadata={
                "source_url": ch.source_url,
                "title": ch.title,
                "section_path": ch.section_path,
                "modality": ch.modality,
                "image_url": ch.image_url,
                "text": ch.text[:1000],
            },
        ))
        stats["text" if ch.modality == "text" else "image"] += 1

    added = store.upsert(records)
    store.save()
    stats["upserted"] = added
    return stats
