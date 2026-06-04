from cortexcrawler.engine.dedup import TextDedup, content_hash


def test_content_hash_normalizes():
    assert content_hash("Hello,  World!") == content_hash("hello world")
    assert content_hash("a b c") != content_hash("a b d")


def test_exact_duplicate_detected():
    d = TextDedup(enabled=False, threshold=0.85)
    assert d.is_duplicate("the quick brown fox") is False
    assert d.is_duplicate("the quick brown fox") is True


def test_near_duplicate_detected():
    d = TextDedup(enabled=True, threshold=0.6)
    base = " ".join(f"word{i}" for i in range(40))
    assert d.is_duplicate(base) is False
    # almost identical (one extra token) -> near-dup
    assert d.is_duplicate(base + " extra") is True


def test_distinct_text_not_duplicate():
    d = TextDedup(enabled=True, threshold=0.85)
    assert d.is_duplicate("completely original sentence one") is False
    assert d.is_duplicate("an entirely different thought here") is False
