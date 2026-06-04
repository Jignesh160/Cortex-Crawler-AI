import time

from cortexcrawler.engine.politeness import Politeness


def test_robots_disabled_allows_all():
    p = Politeness("UA", obey_robots=False, rate_limit_per_domain=0.0)
    assert p.allowed("https://anything.example/path") is True


def test_rate_limit_waits_between_same_domain_hits():
    p = Politeness("UA", obey_robots=False, rate_limit_per_domain=0.2)
    url = "https://example.com/a"
    p.wait(url)  # first hit: no wait
    start = time.monotonic()
    p.wait(url)  # second hit: must wait ~0.2s
    assert time.monotonic() - start >= 0.18


def test_domain_extraction():
    p = Politeness("UA", obey_robots=False, rate_limit_per_domain=0.0)
    assert p._domain("https://sub.example.com:8080/x") == "sub.example.com:8080"
