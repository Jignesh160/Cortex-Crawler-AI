"""Fetch dispatcher (ARCHITECTURE_FINAL.md §3).

Phase 1 = static fetch via httpx. A Playwright fallback (for JS-heavy pages) plugs
in here later behind the same FetchResult contract, triggered when static yield is
too thin.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass

import httpx

from ..log import get_logger
from .politeness import Politeness

_log = get_logger("fetch")


@dataclass
class FetchResult:
    url: str            # final URL after redirects
    status: int
    html: str
    content_type: str
    ok: bool


class Fetcher:
    def __init__(self, politeness: Politeness, timeout: float, user_agent: str,
                 max_retries: int = 3):
        self.politeness = politeness
        self.max_retries = max(1, max_retries)
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            http2=True,
        )

    def _get(self, url: str) -> httpx.Response | None:
        """GET with bounded retry + exponential backoff on transient errors / 5xx / 429."""
        delay = 0.5
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.get(url)
            except httpx.HTTPError as exc:
                if attempt == self.max_retries:
                    _log.warning("fetch failed %s: %s", url, exc)
                    return None
            else:
                if resp.status_code < 500 and resp.status_code != 429:
                    return resp
                if attempt == self.max_retries:
                    return resp
                _log.info("transient %s on %s (attempt %d), retrying",
                          resp.status_code, url, attempt)
            time.sleep(delay + random.uniform(0, delay / 2))
            delay *= 2
        return None

    def fetch(self, url: str) -> FetchResult | None:
        """Return a FetchResult, or None if disallowed/failed."""
        if not self.politeness.allowed(url):
            _log.info("robots disallowed: %s", url)
            return None
        self.politeness.wait(url)
        resp = self._get(url)
        if resp is None:
            return None

        ctype = resp.headers.get("content-type", "").split(";")[0].strip()
        is_html = "html" in ctype or ctype == ""
        return FetchResult(
            url=str(resp.url),
            status=resp.status_code,
            html=resp.text if is_html else "",
            content_type=ctype,
            ok=resp.is_success and is_html,
        )

    def fetch_bytes(self, url: str) -> tuple[bytes, str] | None:
        """Fetch raw bytes (used for images). Returns (bytes, content_type)."""
        self.politeness.wait(url)
        resp = self._get(url)
        if resp is None or not resp.is_success:
            return None
        ctype = resp.headers.get("content-type", "").split(";")[0].strip()
        return resp.content, ctype

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
