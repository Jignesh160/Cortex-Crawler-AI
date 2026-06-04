"""Dynamic rendering for JS-heavy pages (ARCHITECTURE_FINAL.md §3 — Playwright path).

Used as an automatic fallback: the crawler tries a fast static fetch first, and only
spins up a headless browser when a page comes back thin (a sign its content is
rendered by JavaScript). Reuses one browser across the run for speed.

Optional dependency: install with `pip install "cortexcrawler[dynamic]"` then
`playwright install chromium`. If unavailable, DynamicRenderer.create() returns None
and the crawler simply skips the fallback.
"""
from __future__ import annotations

from ..log import get_logger

_log = get_logger("dynamic")


class DynamicRenderer:
    def __init__(self, user_agent: str, timeout: float,
                 wait_ms: int = 2000, scroll: bool = True, max_scrolls: int = 8):
        from playwright.sync_api import sync_playwright  # lazy: only when used
        self.user_agent = user_agent
        self.timeout_ms = int(timeout * 1000)
        self.wait_ms = wait_ms
        self.scroll = scroll
        self.max_scrolls = max_scrolls
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)

    @classmethod
    def create(cls, *args, **kwargs) -> "DynamicRenderer | None":
        """Build a renderer, or return None if Playwright/Chromium isn't available."""
        try:
            return cls(*args, **kwargs)
        except Exception as exc:  # ImportError, browser not installed, etc.
            _log.warning("dynamic rendering unavailable (%s); install with "
                         "pip install 'cortexcrawler[dynamic]' && playwright install chromium",
                         type(exc).__name__)
            return None

    def render(self, url: str) -> str | None:
        """Return fully-rendered HTML, or None on failure."""
        ctx = self._browser.new_context(user_agent=self.user_agent)
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            if self.scroll:  # trigger lazy-load / infinite scroll
                last_h = 0
                for _ in range(self.max_scrolls):
                    page.mouse.wheel(0, 20000)
                    page.wait_for_timeout(400)
                    h = page.evaluate("document.body.scrollHeight")
                    if h == last_h:
                        break
                    last_h = h
            if self.wait_ms:
                page.wait_for_timeout(self.wait_ms)
            return page.content()
        except Exception as exc:
            _log.warning("dynamic render failed %s: %s", url, exc)
            return None
        finally:
            ctx.close()

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._pw.stop()
