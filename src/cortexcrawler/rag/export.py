"""Emit RAG-ready chunks so consumers don't have to re-chunk the markdown.

Writes one JSON record per line (JSONL). Each record:
    {chunk_id, text, heading, section_path, source_url, title, topic,
     modality, image_url, images}

`topic` is the page-level subject (the page title); `heading` is the chunk's
section. `images` lists image URLs that belong to the same page section.
"""
from __future__ import annotations

import json
from pathlib import Path

from .chunk import chunk_knowledge


def export_chunks(knowledge_root: str, out_path: str,
                  target_tokens: int = 500) -> dict:
    root = Path(knowledge_root)
    chunks = chunk_knowledge(root, target_tokens=target_tokens)

    # Group image chunks per page so text chunks can reference their page images.
    images_by_page: dict[str, list[str]] = {}
    for c in chunks:
        if c.modality == "image" and c.image_url:
            images_by_page.setdefault(c.source_url, []).append(c.image_url)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_text = n_image = 0
    with out.open("w", encoding="utf-8") as fh:
        for c in chunks:
            rec = {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "heading": c.heading,
                "section_path": c.section_path,
                "source_url": c.source_url,
                "title": c.title,
                "topic": c.title,
                "modality": c.modality,
                "image_url": c.image_url,
                "images": images_by_page.get(c.source_url, []) if c.modality == "text" else [],
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if c.modality == "text":
                n_text += 1
            else:
                n_image += 1
    return {"path": str(out), "text": n_text, "image": n_image,
            "total": n_text + n_image}
