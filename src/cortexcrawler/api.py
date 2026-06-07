"""Public API facade — the surface your chatbot imports.

    from cortexcrawler import KnowledgeBase

    kb = KnowledgeBase()                       # built-in defaults (+ optional config)
    paths = kb.crawl("https://your-site.com/") # site -> knowledge/<site>/*.md + images/

CortexCrawler's job ends at clean markdown + downloaded images. Your own RAG
pipeline handles chunking / embedding / retrieval from the knowledge/ folder.
"""
from __future__ import annotations

from dataclasses import dataclass

from .engine.config import Config, load_config
from .engine.crawl import Crawler


@dataclass
class KnowledgeBase:
    config: Config | None = None

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = load_config()

    def crawl(self, seed_url: str) -> list[str]:
        """Crawl a site into knowledge/<site>/*.md (+ images). Returns written paths."""
        return Crawler(self.config).crawl(seed_url)
