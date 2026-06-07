"""CortexCrawler AI — crawl websites into clean markdown + images for RAG.

Produces one .md per page (with provenance front-matter) plus deduplicated,
quality-filtered images. Chunking/embedding/retrieval are intentionally out of
scope — your RAG pipeline consumes the knowledge/ folder.

Public API:
    from cortexcrawler import KnowledgeBase
"""
from .api import KnowledgeBase
from .engine.config import Config, load_config

__version__ = "0.1.0"
__all__ = ["KnowledgeBase", "Config", "load_config", "__version__"]
