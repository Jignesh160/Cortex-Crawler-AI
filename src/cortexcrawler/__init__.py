"""CortexCrawler AI — multimodal RAG knowledge-base builder.

Public API:
    from cortexcrawler import KnowledgeBase
"""
from .api import KnowledgeBase
from .engine.config import Config, load_config

__version__ = "0.1.0"
__all__ = ["KnowledgeBase", "Config", "load_config", "__version__"]
