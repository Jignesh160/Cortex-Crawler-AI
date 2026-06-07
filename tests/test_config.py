from cortexcrawler.engine.config import load_config


def test_defaults_self_contained(tmp_path, monkeypatch):
    # No config file, no env -> built-in defaults must work.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CORTEX_CONFIG", raising=False)
    cfg = load_config()
    assert cfg.crawl["max_pages"] == 50
    assert cfg.crawl["obey_robots"] is False
    assert cfg.images["min_width"] == 100
    assert cfg.output["root"] == "knowledge"


def test_file_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "custom.yaml"
    p.write_text("crawl:\n  max_pages: 7\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.crawl["max_pages"] == 7
    # untouched keys keep defaults
    assert cfg.crawl["max_depth"] == 2


def test_missing_config_file_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")
