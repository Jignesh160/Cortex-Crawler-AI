"""Dynamic-fallback config defaults. (The live browser path is verified via an
end-to-end crawl, not unit tests, to avoid launching Chromium in CI.)"""
from cortexcrawler.engine.config import load_config


def test_dynamic_fallback_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CORTEX_CONFIG", raising=False)
    cfg = load_config()
    assert cfg.crawl["dynamic_fallback"] is True
    assert cfg.crawl["dynamic_min_chars"] == 200
    assert "dynamic_wait_ms" in cfg.crawl
