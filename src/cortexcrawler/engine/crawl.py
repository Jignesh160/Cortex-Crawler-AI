"""Deep-crawl orchestrator (ARCHITECTURE_FINAL.md §3, §0B).

BFS frontier with URL normalization/dedup, scope (same registered domain), and depth
limits. Wires together fetch -> extract -> media gate -> text dedup -> emit. This is
the orchestration we own; the heavy lifting lives in the reused primitives.
"""
from __future__ import annotations

import fnmatch
import re
from collections import deque
from pathlib import Path
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


def _in_scope(url: str, include: list[str], exclude: list[str]) -> bool:
    """URL passes scope if it matches no exclude glob and (if include is set) at
    least one include glob. Globs match against the full URL and its path."""
    path = urlsplit(url).path
    candidates = (url, path)
    for pat in exclude or []:
        if any(fnmatch.fnmatch(c, pat) for c in candidates):
            return False
    if include:
        return any(fnmatch.fnmatch(c, pat) for pat in include for c in candidates)
    return True


def _top_lines(md: str, k: int = 3) -> list[str]:
    """First k non-empty lines of a page body (where header/nav chrome sits)."""
    out: list[str] = []
    for ln in md.splitlines():
        s = ln.strip()
        if s:
            out.append(s)
        if len(out) >= k:
            break
    return out


def _global_boilerplate(per_page_top: list[list[str]], min_frac: float = 0.8) -> set[str]:
    """Lines that appear at the top of (almost) every page = site chrome.

    Conservative: only considers the first few lines per page (so mid-page
    section headings like 'Specifications' are never treated as boilerplate),
    and requires a high cross-page frequency.
    """
    from collections import Counter
    n = len(per_page_top)
    if n < 3:
        return set()
    counts: Counter[str] = Counter()
    for lines in per_page_top:
        for s in set(lines):  # unique per page
            counts[s] += 1
    threshold = max(2, int(min_frac * n + 0.9999))
    return {line for line, c in counts.items() if c >= threshold}


def _strip_lines(md: str, drop: set[str]) -> str:
    """Remove exact-match boilerplate lines; collapse the blank gaps they leave."""
    if not drop:
        return md
    kept = [ln for ln in md.splitlines() if ln.strip() not in drop]
    text = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


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
        include = c.get("include", [])
        exclude = c.get("exclude", [])
        seed_domain = _registered_domain(seed)

        queue: deque[tuple[str, int]] = deque([(_normalize(seed), 0)])
        seen: set[str] = {_normalize(seed)}
        written: list[str] = []
        page_tops: list[list[str]] = []   # top lines per page, for boilerplate detection

        while queue and len(written) < max_pages:
            url, depth = queue.popleft()
            if not _in_scope(url, include, exclude):
                _log.debug("scope: excluded %s", url)
                continue
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
            page_tops.append(_top_lines(ext.markdown))
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

        # Cross-page cleanup: strip site-title / nav chrome that repeats on (nearly)
        # every page, so it doesn't leak into each page's content.
        boilerplate = _global_boilerplate(page_tops)
        if boilerplate:
            _log.info("stripping %d global boilerplate line(s) across %d pages",
                      len(boilerplate), len(written))
            for fp in written:
                p = Path(fp)
                cleaned = _strip_lines(p.read_text(encoding="utf-8"), boilerplate)
                p.write_text(cleaned, encoding="utf-8")
        return written
