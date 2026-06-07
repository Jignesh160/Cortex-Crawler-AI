"""Public API facade — the surface your chatbot imports.

    from cortexcrawler import KnowledgeBase

    kb = KnowledgeBase()                 # uses built-in defaults (+ optional config/env)
    kb.crawl("https://your-site.com/")   # site -> knowledge/*.md + images
    kb.index()                           # knowledge/ -> vector index
    for hit in kb.search("question"):    # retrieve citable chunks
        print(hit.metadata["source_url"], hit.score)
    print(kb.ask("question"))            # grounded, cited answer (Nova if configured)

Backends (local vs Bedrock/S3 Vectors) are chosen by config/env, never by code here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .engine.config import Config, load_config
from .engine.crawl import Crawler
from .rag.answer import answer as _answer
from .rag.embed import Embedder, get_embedder
from .rag.index import build_index
from .rag.retrieve import retrieve as _retrieve
from .rag.store import Hit, VectorStore, get_store


@dataclass
class KnowledgeBase:
    config: Config | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_config()
        self._embedder: Embedder | None = None
        self._store: VectorStore | None = None

    @classmethod
    def for_aws(
        cls,
        bucket: str,
        index: str = "cortex-kb",
        region: str | None = None,
        *,
        answer_with_nova: bool = False,
        embed_model: str = "amazon.titan-embed-image-v1",
        nova_model: str = "amazon.nova-lite-v1:0",
        embed_dim: int = 1024,
    ) -> "KnowledgeBase":
        """Configure the AWS backends explicitly (no env vars or .env needed).

        Credentials are inherited from the host process via boto3's standard chain
        (env vars / IAM role / instance profile) — nothing to pass here.

        Set answer_with_nova=False (default) to use retrieval only (`.search()`),
        letting your own chatbot LLM generate the answer.
        """
        cfg = load_config()
        rag = cfg.raw["rag"]
        rag["embedder"] = {"backend": "bedrock", "model_id": embed_model,
                           "region": region, "dim": embed_dim}
        rag["store"] = {"backend": "s3vectors", "bucket": bucket, "index": index,
                        "region": region, "dim": embed_dim}
        rag["answer"] = ({"backend": "bedrock", "model_id": nova_model, "region": region}
                         if answer_with_nova else {"backend": "local"})
        return cls(config=cfg)

    # --- lazy singletons so the chatbot can construct once and reuse ---
    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = get_embedder(self.config.rag.get("embedder", {}))
        return self._embedder

    @property
    def store(self) -> VectorStore:
        if self._store is None:
            self._store = get_store(self.config.rag.get("store", {}))
        return self._store

    # --- pipeline operations ---
    def crawl(self, seed_url: str) -> list[str]:
        """Crawl a site into knowledge/*.md (+ images). Returns written file paths."""
        return Crawler(self.config).crawl(seed_url)

    def crawl_and_chunk(self, seed_url: str,
                        chunks_path: str = "datasets/chunks.jsonl") -> dict[str, Any]:
        """Crawl a site to .md + images, then auto-export RAG chunks. Returns stats."""
        from .rag.export import export_chunks
        written = self.crawl(seed_url)
        stats = export_chunks(
            self.config.output.get("root", "knowledge"), chunks_path,
            target_tokens=self.config.rag.get("chunk_target_tokens", 500))
        stats["pages"] = len(written)
        return stats

    def index(self) -> dict[str, Any]:
        """Build/refresh the vector index from knowledge/. Returns stats."""
        rag = self.config.rag
        return build_index(
            knowledge_root=self.config.output.get("root", "knowledge"),
            embedder=self.embedder,
            store=self.store,
            target_tokens=rag.get("chunk_target_tokens", 500),
            semantic_threshold=rag.get("semantic_dedup_threshold", 0.97),
        )

    def search(self, query: str, top_k: int = 5,
               modality: str | None = None) -> list[Hit]:
        """Retrieve citable chunks for a query (no LLM)."""
        return _retrieve(query, self.embedder, self.store, top_k=top_k, modality=modality)

    def ask(self, query: str, top_k: int = 5,
            modality: str | None = None) -> str:
        """Retrieve + synthesize a grounded, cited answer."""
        hits = self.search(query, top_k=top_k, modality=modality)
        return _answer(query, hits, self.config.rag.get("answer", {}))
