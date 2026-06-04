"""Tier 3: crawl scope include/exclude glob filtering."""
from cortexcrawler.engine.crawl import _in_scope

EXCLUDE = ["*/cookies*", "*/legalNotice", "*/privacy*", "*/request-for-quote*"]


def test_excluded_urls_blocked():
    assert not _in_scope("https://x.com/legalNotice", [], EXCLUDE)
    assert not _in_scope("https://x.com/cookies-policy", [], EXCLUDE)
    assert not _in_scope("https://x.com/request-for-quote?model=v27", [], EXCLUDE)


def test_content_urls_allowed():
    assert _in_scope("https://x.com/iCAURV27REEV", [], EXCLUDE)
    assert _in_scope("https://x.com/models/v27", [], EXCLUDE)


def test_include_restricts_when_set():
    inc = ["*/models/*"]
    assert _in_scope("https://x.com/models/v27", inc, EXCLUDE)
    assert not _in_scope("https://x.com/about", inc, EXCLUDE)


def test_exclude_wins_over_include():
    assert not _in_scope("https://x.com/models/privacy", ["*/models/*"], ["*/privacy*"])
