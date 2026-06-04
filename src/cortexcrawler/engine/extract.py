"""Content extraction (ARCHITECTURE_FINAL.md §3).

HTML -> clean markdown via trafilatura (the reusable primitive), plus our own image
discovery pass that pulls <img> tags from the main content with alt/caption/context.
We own the orchestration; we stand on trafilatura + BeautifulSoup for the plumbing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup


@dataclass
class DiscoveredImage:
    src_url: str
    alt: str = ""
    caption: str = ""
    surrounding_text: str = ""


@dataclass
class Extraction:
    title: str
    lang: str
    markdown: str
    text_len: int
    images: list[DiscoveredImage] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # for the crawl frontier


_WS = re.compile(r"\s+")


def _clean(text: str | None) -> str:
    return _WS.sub(" ", (text or "")).strip()


def _discover_images(html: str, base_url: str) -> list[DiscoveredImage]:
    soup = BeautifulSoup(html, "lxml")
    out: list[DiscoveredImage] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        abs_src = urljoin(base_url, src)
        if abs_src in seen:
            continue
        seen.add(abs_src)

        alt = _clean(img.get("alt"))
        # caption: a nearby <figcaption>, else the parent's text as context
        caption = ""
        fig = img.find_parent("figure")
        if fig and fig.find("figcaption"):
            caption = _clean(fig.find("figcaption").get_text())
        parent = img.find_parent(["figure", "p", "div", "section"])
        surrounding = _clean(parent.get_text()) if parent else ""
        surrounding = surrounding[:500]

        out.append(DiscoveredImage(abs_src, alt, caption, surrounding))
    return out


def _discover_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0]
        if href.startswith(("http://", "https://")) and href not in seen:
            seen.add(href)
            links.append(href)
    return links


def extract(html: str, url: str) -> Extraction:
    # Primary text extraction -> markdown (headings/lists/tables preserved).
    md = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_links=True,
        favor_recall=True,
        url=url,
    ) or ""

    meta = trafilatura.extract_metadata(html)
    title = (meta.title if meta and meta.title else "") or "Untitled"
    lang = (meta.language if meta and getattr(meta, "language", None) else "") or ""

    return Extraction(
        title=_clean(title),
        lang=lang,
        markdown=md.strip(),
        text_len=len(md),
        images=_discover_images(html, url),
        links=_discover_links(html, url),
    )
