"""Use CortexCrawler from your own RAG pipeline.

CortexCrawler's job: turn a site into clean .md + downloaded images.
Your chatbot's job: chunk / embed / retrieve from the knowledge/ folder.
"""
import json
from pathlib import Path

from cortexcrawler import KnowledgeBase


def crawl_site(url: str) -> list[str]:
    kb = KnowledgeBase()                 # built-in defaults (config/settings.yaml optional)
    return kb.crawl(url)                 # -> knowledge/<site>/*.md (+ images/)


def feed_into_your_rag(knowledge_root: str = "knowledge") -> None:
    """Walk the output and hand it to YOUR existing chunker/ingester."""
    for md in Path(knowledge_root).rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        # front-matter (--- ... ---) carries source_url/title for citations;
        # body is clean markdown; images are referenced as images/<sha>.<ext>
        your_ingest_text(text, source_file=str(md))

        # image metadata lives next to each image as a JSON sidecar
        for sidecar in (md.parent / "images").glob("*.json"):
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            your_ingest_image(meta["s3_url"], alt=meta["alt"], page_url=meta["page_url"])


def your_ingest_text(markdown: str, source_file: str) -> None:
    ...  # your chunking + embedding here


def your_ingest_image(image_ref: str, alt: str, page_url: str) -> None:
    ...  # your multimodal ingest here


if __name__ == "__main__":
    crawl_site("https://cherybahrain.com/")
    feed_into_your_rag()
