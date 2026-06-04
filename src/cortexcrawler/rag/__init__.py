"""CortexCrawler RAG layer (Phase 2).

Reads the canonical markdown under `knowledge/` and builds a retrievable index.
IMPORTANT (architecture contract): this package reads files only and MUST NOT import
from `engine/`. That boundary is what makes the crawl engine swappable.
"""

__version__ = "0.1.0"
