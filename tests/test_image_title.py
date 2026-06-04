"""Tier 3: image title falls back alt -> caption -> surrounding_text."""
from cortexcrawler.engine.emit import _image_title
from cortexcrawler.engine.extract import DiscoveredImage


def test_prefers_alt():
    img = DiscoveredImage("u", alt="Front fascia", caption="cap", surrounding_text="ctx")
    assert _image_title(img) == "Front fascia"


def test_falls_back_to_caption():
    img = DiscoveredImage("u", alt="", caption="Sculpted profile", surrounding_text="ctx")
    assert _image_title(img) == "Sculpted profile"


def test_falls_back_to_surrounding_text():
    img = DiscoveredImage("u", alt="", caption="",
                          surrounding_text="The premium interior features ambient lighting throughout the cabin space.")
    out = _image_title(img)
    assert out.startswith("The premium interior")
    assert len(out) <= 81


def test_defaults_to_image():
    assert _image_title(DiscoveredImage("u", alt="", caption="", surrounding_text="")) == "image"
