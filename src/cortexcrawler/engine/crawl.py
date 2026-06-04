"""Deep-crawl orchestrator (ARCHITECTURE_FINAL.md §3, §0B).

BFS frontier with URL normalization/dedup, scope (same registered domain), and depth
limits. Wires together fetch -> extract -> media gate -> text dedup -> emit. This is
the orchestration we own; the heavy lifting lives in the reused primitives.
"""
from __future__ import annotations

from collections import deque
from urllib.parse import urlsplit, urlunsplit

import tldextract

from ..log import get_logger
from .config import Config
from .dedup import TextDedup, content_hash
from .emit import Emitter
from .extract import extract
from .fetch import Fetcher
from .media import MediaPipeline
from .politeness import Politeness

_log = get_logger("crawl")


def _normalize(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or "/", "", ""))


def _registered_domain(url: str) -> str:
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}"


class Crawler:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        c = cfg.crawl
        self.politeness = Politeness(
            user_agent=c.get("user_agent", "CortexCrawlerBot/0.1"),
            obey_robots=c.get("obey_robots", True),
            rate_limit_per_domain=c.get("rate_limit_per_domain", 1.0),
        )
        self.fetcher = Fetcher(self.politeness, c.get("timeout", 20.0),
                               c.get("user_agent", "CortexCrawlerBot/0.1"),
                               max_retries=c.get("max_retries", 3))
        self.media = MediaPipeline(cfg.images)
        self.text_dedup = TextDedup(
            enabled=cfg.dedup.get("text_near_dup", True),
            threshold=cfg.dedup.get("minhash_threshold", 0.85),
        )
        self.emitter = Emitter(cfg.output.get("root", "knowledge"),
                               cfg.output.get("image_base_url", ""))
        self.min_text = cfg.extract.get("min_text_chars", 200)
        self.images_enabled = cfg.images.get("enabled", True)

        # Dynamic (JS) rendering — created lazily on first thin page.
        self.dynamic_enabled = c.get("dynamic_fallback", True)
        self.dynamic_min_chars = c.get("dynamic_min_chars", 200)
        self.dynamic_wait_ms = c.get("dynamic_wait_ms", 2000)
        self._dynamic = None          # DynamicRenderer | None (lazy)
        self._dynamic_tried = False   # only attempt to launch once per run

    def _maybe_render(self, url: str) -> str | None:
        """Launch (once) and use the headless browser for a JS-heavy page."""
        if not self.dynamic_enabled or not self.politeness.allowed(url):
            return None
        if self._dynamic is None and not self._dynamic_tried:
            from .dynamic import DynamicRenderer
            self._dynamic_tried = True
            c = self.cfg.crawl
            self._dynamic = DynamicRenderer.create(
                user_agent=c.get("user_agent", "CortexCrawlerBot/0.1"),
                timeout=c.get("timeout", 20.0), wait_ms=self.dynamic_wait_ms)
        if self._dynamic is None:
            return None
        _log.info("dynamic render (JS fallback): %s", url)
        self.politeness.wait(url)
        return self._dynamic.render(url)

    def crawl(self, seed: str) -> list[str]:
        c = self.cfg.crawl
        max_pages = c.get("max_pages", 50)
        max_depth = c.get("max_depth", 2)
        same_domain = c.get("same_domain_only", True)
        seed_domain = _registered_domain(seed)

        queue: deque[tuple[str, int]] = deque([(_normalize(seed), 0)])
        seen: set[str] = {_normalize(seed)}
        written: list[str] = []

        while queue and len(written) < max_pages:
            url, depth = queue.popleft()
            _log.info("crawl d%d %s", depth, url)
            try:
                res = self.fetcher.fetch(url)
            except Exception:  # defensive: one bad page must not kill the run
                _log.exception("unexpected error fetching %s", url)
                continue
            final_url = res.url if res else url
            ext = extract(res.html, final_url) if (res and res.ok) else None

            # JS fallback: if static yield is thin (or fetch failed), render in a
            # real browser and keep whichever extraction is richer.
            if ext is None or ext.text_len < self.dynamic_min_chars:
                dhtml = self._maybe_render(final_url)
                if dhtml:
                    dext = extract(dhtml, final_url)
                    if dext and (ext is None or dext.text_len > ext.text_len):
                        ext = dext

            if ext is None or ext.text_len == 0:
                _log.debug("skip (no extractable content): %s", url)
                continue

            # Quality: too-thin pages are marked, not silently kept.
            status = "ok" if ext.text_len >= self.min_text else "partial"

            # Tier 1/2 text dedup across pages.
            if self.text_dedup.is_duplicate(ext.markdown):
                _log.debug("dedup: duplicate page content, skipped %s", url)
                continue

            # Image quality gate + dedup.
            kept = []
            if self.images_enabled:
                for disc in ext.images:
                    verdict = self.media.process(self.fetcher, disc)
                    if verdict.kept:
                        kept.append(verdict.kept)
                _log.info("media: kept %d/%d images", len(kept), len(ext.images))

            path = self.emitter.write_page(
                url=res.url, title=ext.title, lang=ext.lang, markdown=ext.markdown,
                content_hash=content_hash(ext.markdown), kept_images=kept,
                status=status, depth=depth,
            )
            written.append(str(path))
            _log.info("emit: %s", path)

            # Expand frontier.
            if depth < max_depth:
                for link in ext.links:
                    n = _normalize(link)
                    if n in seen:
                        continue
                    if same_domain and _registered_domain(n) != seed_domain:
                        continue
                    seen.add(n)
                    queue.append((n, depth + 1))

        self.fetcher.close()
        if self._dynamic is not None:
            self._dynamic.close()
        return written
