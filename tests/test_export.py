"""Tier 4: RAG-ready chunks.jsonl export."""
import json

from cortexcrawler.rag.export import export_chunks

PAGE = """---
source_url: https://example.com/v27
title: iCAUR V27
content_hash: abc123def456
---

## Design
Bold lines and a sculpted profile with premium materials throughout the cabin.

## Performance
Dual motor all wheel drive delivers a combined power of 449 horsepower easily.

## Images

![front fascia](images/aaa.png)
"""


def test_export_chunks_jsonl(tmp_path):
    kb = tmp_path / "knowledge" / "example.com"
    kb.mkdir(parents=True)
    (kb / "v27.md").write_text(PAGE, encoding="utf-8")

    out = tmp_path / "chunks.jsonl"
    stats = export_chunks(str(tmp_path / "knowledge"), str(out))
    assert out.exists()
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(records) == stats["total"]

    text_recs = [r for r in records if r["modality"] == "text"]
    headings = {r["heading"] for r in text_recs}
    assert {"Design", "Performance"} <= headings
    for r in text_recs:
        assert r["source_url"] == "https://example.com/v27"
        assert r["topic"] == "iCAUR V27"
        assert "text" in r and r["text"]
        # text chunks reference their page's images
        assert "images/aaa.png" in r["images"]

    img_recs = [r for r in records if r["modality"] == "image"]
    assert any(r["image_url"] == "images/aaa.png" for r in img_recs)
