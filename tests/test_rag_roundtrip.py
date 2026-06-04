"""End-to-end RAG test on the local backends: index a tiny knowledge dir and query it."""
import numpy as np

from cortexcrawler.rag.embed import LocalEmbedder
from cortexcrawler.rag.semantic_dedup import SemanticDedup
from cortexcrawler.rag.store import LocalVectorStore, Record

KB = """---
source_url: https://example.com/cats
title: Cats
content_hash: cat0001
lang: en
status: ok
---

# Cats

Cats are small domestic felines that purr and chase mice.
"""


def test_local_embedder_deterministic_and_normalized():
    e = LocalEmbedder(dim=256)
    a, b = e.embed_text("hello world"), e.embed_text("hello world")
    assert np.allclose(a, b)
    assert abs(np.linalg.norm(a) - 1.0) < 1e-5


def test_store_roundtrip_and_query(tmp_path):
    e = LocalEmbedder(dim=256)
    store = LocalVectorStore(path=str(tmp_path / "store"))
    store.upsert([
        Record("c1", e.embed_text("cats purr and chase mice"),
               {"modality": "text", "source_url": "u1", "text": "cats"}),
        Record("c2", e.embed_text("rockets fly to orbit"),
               {"modality": "text", "source_url": "u2", "text": "rockets"}),
    ])
    store.save()

    # persisted store reloads
    store2 = LocalVectorStore(path=str(tmp_path / "store"))
    hits = store2.query(e.embed_text("feline that chases mice"), top_k=1)
    assert hits and hits[0].id == "c1"


def test_semantic_dedup_gate():
    e = LocalEmbedder(dim=256)
    gate = SemanticDedup(threshold=0.95)
    v = e.embed_text("the exact same sentence")
    assert gate.is_duplicate(v) is False
    assert gate.is_duplicate(v) is True  # identical vector -> dup


def test_index_build_local(tmp_path):
    from cortexcrawler.rag.index import build_index

    root = tmp_path / "knowledge" / "example.com"
    root.mkdir(parents=True)
    (root / "cats.md").write_text(KB, encoding="utf-8")

    e = LocalEmbedder(dim=256)
    store = LocalVectorStore(path=str(tmp_path / "idx"))
    stats = build_index(str(tmp_path / "knowledge"), e, store)
    assert stats["upserted"] >= 1
    hits = store.query(e.embed_text("domestic feline"), top_k=1)
    assert hits and hits[0].metadata["source_url"] == "https://example.com/cats"
