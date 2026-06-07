"""Auto-rebuild chunks.jsonl when .md files change."""
import json

from cortexcrawler.rag.watch import snapshot, watch_and_export

FM = "---\nsource_url: https://example.com/p\ntitle: P\ncontent_hash: abc123def456\n---\n\n"


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_initial_export(tmp_path):
    kb = tmp_path / "knowledge" / "example.com"
    kb.mkdir(parents=True)
    (kb / "p.md").write_text(FM + "## Design\nBold lines and sculpted profile here.\n", encoding="utf-8")
    out = tmp_path / "chunks.jsonl"
    stats = watch_and_export(str(tmp_path / "knowledge"), str(out), run_once=True)
    assert out.exists() and stats["total"] >= 1


def test_snapshot_detects_edit(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir()
    f = kb / "a.md"
    f.write_text(FM + "## A\nfirst.\n", encoding="utf-8")
    snap1 = snapshot(str(kb))
    # rewrite with a newer mtime
    import os
    import time
    time.sleep(0.01)
    f.write_text(FM + "## A\nfirst.\n\n## B\nsecond section added here.\n", encoding="utf-8")
    os.utime(f, None)
    snap2 = snapshot(str(kb))
    assert snap1 != snap2


def test_reexport_reflects_new_section(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir()
    f = kb / "a.md"
    f.write_text(FM + "## Design\nbold profile lines here today.\n", encoding="utf-8")
    out = tmp_path / "chunks.jsonl"
    watch_and_export(str(kb), str(out), run_once=True)
    before = len(_records(out))
    # author adds a section
    f.write_text(FM + "## Design\nbold profile lines here today.\n\n"
                      "## Safety\nairbags and strong structure throughout cabin.\n", encoding="utf-8")
    watch_and_export(str(kb), str(out), run_once=True)
    after = _records(out)
    assert len(after) > before
    assert any(r["heading"] == "Safety" for r in after)
