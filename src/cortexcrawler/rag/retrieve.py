"""Retrieval (ARCHITECTURE_FINAL.md §3).

Embed the query with the SAME embedder used to index, search the vector store, and
return citable hits. Optional modality filter (text-only / image-only).
"""
from __future__ import annotations

from .embed import Embedder
from .store import Hit, VectorStore


def retrieve(query: str, embedder: Embedder, store: VectorStore,
             top_k: int = 5, modality: str | None = None) -> list[Hit]:
    qv = embedder.embed_text(query)
    return store.query(qv, top_k=top_k, modality=modality)
