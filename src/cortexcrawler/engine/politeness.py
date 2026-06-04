"""Compliance & politeness layer (ARCHITECTURE_FINAL.md §9).

robots.txt obedience + per-domain rate limiting. Honest User-Agent is set by the
fetcher. This is mandatory for a crawler that redistributes content.
"""
from __future__ import annotations

import time
import urllib.robotparser as robotparser
from urllib.parse import urlsplit, urlunsplit


class Politeness:
    def __init__(self, user_agent: str, obey_robots: bool, rate_limit_per_domain: float):
        self.user_agent = user_agent
        self.obey_robots = obey_robots
        self.rate_limit = rate_limit_per_domain
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}

    @staticmethod
    def _domain(url: str) -> str:
        return urlsplit(url).netloc

    def _robots_for(self, url: str) -> robotparser.RobotFileParser | None:
        domain = self._domain(url)
        if domain in self._robots:
            return self._robots[domain]
        parts = urlsplit(url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
        except Exception:
            rp = None  # robots unreachable -> fail open but log via caller
        self._robots[domain] = rp
        return rp

    def allowed(self, url: str) -> bool:
        if not self.obey_robots:
            return True
        rp = self._robots_for(url)
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    def wait(self, url: str) -> None:
        """Block until the per-domain rate limit permits a request."""
        domain = self._domain(url)
        last = self._last_hit.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self.rate_limit:
                time.sleep(self.rate_limit - elapsed)
        self._last_hit[domain] = time.monotonic()
