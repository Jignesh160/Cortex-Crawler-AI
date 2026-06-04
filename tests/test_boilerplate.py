"""Tier 3: strip global site-title / nav artifacts repeating across pages."""
from cortexcrawler.engine.crawl import _global_boilerplate, _strip_lines, _top_lines


def test_global_boilerplate_detects_repeated_header():
    pages = [
        ["# iCAUR INTERNATIONAL WEB", "Design", "Bold lines."],
        ["# iCAUR INTERNATIONAL WEB", "Performance", "Strong torque."],
        ["# iCAUR INTERNATIONAL WEB", "Safety", "Airbags."],
        ["# iCAUR INTERNATIONAL WEB", "Specifications", "Range."],
    ]
    bp = _global_boilerplate(pages)
    assert "# iCAUR INTERNATIONAL WEB" in bp
    # genuine per-page section headings must NOT be flagged
    assert "Design" not in bp
    assert "Specifications" not in bp


def test_global_boilerplate_needs_enough_pages():
    assert _global_boilerplate([["X"], ["X"]]) == set()  # < 3 pages: no judgement


def test_strip_lines_removes_and_collapses():
    md = "# iCAUR INTERNATIONAL WEB\n\n# Real Title\n\nReal content here.\n"
    out = _strip_lines(md, {"# iCAUR INTERNATIONAL WEB"})
    assert "iCAUR INTERNATIONAL WEB" not in out
    assert "# Real Title" in out and "Real content here." in out
    assert "\n\n\n" not in out  # blank gaps collapsed


def test_top_lines_takes_first_nonempty():
    assert _top_lines("\n\n# Head\n\npara\n\nmore", k=2) == ["# Head", "para"]
