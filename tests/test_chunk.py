from pathlib import Path

from cortexcrawler.engine.dedup import jaccard, shingles
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


_FM = "---\nsource_url: https://example.com/v27\ntitle: V27\ncontent_hash: abc123def456\n---\n\n"


def _write_body(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "page.md"
    p.write_text(_FM + body, encoding="utf-8")
    return p


def test_chunks_split_per_section_with_heading(tmp_path):
    body = (
        "## Design\nBold lines and a sculpted profile with premium materials throughout.\n\n"
        "## Performance\nDual motor all wheel drive with combined power of 449 horsepower.\n\n"
        "## Safety\nHigh strength structure and a comprehensive airbag system on board.\n\n"
        "## Specifications\nTotal range nearly one thousand kilometres with strong torque.\n"
    )
    chunks = [c for c in chunk_file(_write_body(tmp_path, body)) if c.modality == "text"]
    headings = {c.heading for c in chunks}
    assert {"Design", "Performance", "Safety", "Specifications"} <= headings
    assert all(c.heading for c in chunks)  # each chunk carries its heading


def test_intra_page_near_duplicate_removed(tmp_path):
    dup_prose = ("Combined power 449 horsepower, maximum torque 505 newton metres, "
                 "total range 995 kilometres, battery capacity 34.31 kilowatt hours here.")
    dup_table = ("Combined power 449 horsepower maximum torque 505 newton metres "
                 "total range 995 kilometres battery capacity 34.31 kilowatt hours here")
    body = (
        f"## Specifications\n{dup_prose}\n\n"
        f"## Specs Table\n{dup_table}\n\n"
        "## Design\nBold lines and a sculpted profile distinct from the spec content here.\n"
    )
    chunks = [c for c in chunk_file(_write_body(tmp_path, body)) if c.modality == "text"]
    for i, a in enumerate(chunks):
        for b in chunks[i + 1:]:
            sim = jaccard(shingles(a.text), shingles(b.text))
            assert sim <= 0.9, f"near-duplicate chunks remain: {sim:.2f}"
