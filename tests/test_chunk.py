from pathlib import Path

from cortexcrawler.rag.chunk import chunk_file

MD = """---
source_url: https://example.com/doc
title: Example Doc
content_hash: abc123def456
lang: en
status: ok
---

# Example Doc

Intro paragraph about widgets.

## Section One

Details about the first thing.

## Section Two

Details about the second thing.

## Images

![a red widget](images/deadbeef.png)
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "doc.md"
    p.write_text(MD, encoding="utf-8")
    return p


def test_chunks_carry_provenance(tmp_path):
    chunks = chunk_file(_write(tmp_path))
    assert chunks, "expected chunks"
    for c in chunks:
        assert c.source_url == "https://example.com/doc"
        assert c.title == "Example Doc"


def test_heading_sections_become_section_paths(tmp_path):
    chunks = chunk_file(_write(tmp_path))
    paths = {c.section_path for c in chunks if c.modality == "text"}
    assert any("Section One" in p for p in paths)
    assert any("Section Two" in p for p in paths)


def test_image_becomes_image_chunk(tmp_path):
    chunks = chunk_file(_write(tmp_path))
    imgs = [c for c in chunks if c.modality == "image"]
    assert len(imgs) == 1
    assert imgs[0].image_url == "images/deadbeef.png"
    assert imgs[0].text == "a red widget"  # alt text is searchable
