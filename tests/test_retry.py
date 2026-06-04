import pytest

from cortexcrawler.retry import with_retry


def test_retries_then_succeeds():
    calls = {"n": 0}

    @with_retry(attempts=3, base_delay=0.01)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_raises_after_exhausting_attempts():
    @with_retry(attempts=2, base_delay=0.01)
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        always_fail()
