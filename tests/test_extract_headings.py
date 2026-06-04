"""Tier 1: section headings must survive extraction (engine/extract)."""
import re
from pathlib import Path

from cortexcrawler.engine.extract import _inject_headings, extract

FIXTURE = Path(__file__).parent / "fixtures" / "multisection.html"


def _headings(md: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"(?m)^#{1,6}\s+(.*)$", md)]


def test_inject_headings_restores_dropped_sections():
    """Deterministic: simulate Trafilatura output that dropped all headings, and
    confirm we re-insert the real section headings while skipping boilerplate."""
    html = FIXTURE.read_text(encoding="utf-8")
    # Simulate an extractor that kept the main paragraphs but dropped every heading
    # (and dropped nav/footer boilerplate entirely).
    base_md = "\n\n".join([
        "The exterior features distinctive square LED headlights with advanced lighting technology and a commanding presence that blends rugged sophistication with retro-modern character throughout.",
        "Inside you will find a 15.4 inch central touchscreen, an 8.88 inch digital cluster, and premium materials throughout the cabin with configurable ambient lighting for every mood.",
        "A dual-motor all-wheel-drive setup delivers a combined power output of 449 horsepower and 505 newton metres of torque for confident acceleration in all driving conditions.",
        "A high-strength steel body structure, advanced driver assistance systems, and a comprehensive airbag arrangement work together to protect every occupant on board the vehicle.",
        "The total driving range reaches nearly one thousand kilometres while the range-extender architecture keeps the battery charged for long journeys without compromise.",
    ])
    out = _inject_headings(html, base_md)
    heads = _headings(out)
    for section in ("Design", "Performance", "Safety", "Specifications"):
        assert section in heads, f"missing heading: {section}"
    assert len(heads) >= 4
    # Boilerplate headings whose content was NOT kept must not be injected.
    assert "Quick Links" not in heads
    assert "Legal Notice" not in heads


def test_extract_fixture_has_section_headings():
    """End-to-end through extract(): a multi-section page yields >= 4 headings."""
    html = FIXTURE.read_text(encoding="utf-8")
    ex = extract(html, "https://example.com/v27")
    heads = _headings(ex.markdown)
    assert len(heads) >= 4, f"expected >=4 headings, got {heads}"
