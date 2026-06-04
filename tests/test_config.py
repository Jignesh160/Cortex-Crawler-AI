from cortexcrawler.engine.config import load_config


def test_defaults_self_contained(tmp_path, monkeypatch):
    # No config file, no env -> built-in defaults must work.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CORTEX_CONFIG", raising=False)
    cfg = load_config()
    assert cfg.crawl["max_pages"] == 50
    assert cfg.rag["embedder"]["backend"] == "local"
    assert cfg.images["min_width"] == 100


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CORTEX_EMBEDDER_BACKEND", "bedrock")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    cfg = load_config()
    assert cfg.rag["embedder"]["backend"] == "bedrock"
    assert cfg.rag["embedder"]["region"] == "us-east-1"


def test_file_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "custom.yaml"
    p.write_text("crawl:\n  max_pages: 7\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.crawl["max_pages"] == 7
    # untouched keys keep defaults
    assert cfg.crawl["max_depth"] == 2
