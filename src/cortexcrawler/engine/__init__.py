"""CortexCrawler in-house engine — turns a URL into clean markdown + images.

The engine's ONLY downstream-visible output is files under `knowledge/` (see
ARCHITECTURE_FINAL.md §6). Nothing in `rag/` should import from `engine/`.
"""

__version__ = "0.1.0"
