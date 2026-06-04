import io

from PIL import Image

from cortexcrawler.engine.media import MediaPipeline

CFG = {
    "min_width": 100, "min_height": 100, "max_aspect_ratio": 10.0,
    "min_bytes": 100, "allowed_types": ["png", "jpg", "jpeg"],
    "phash_hamming_threshold": 6,
}


def _png(w, h, color=(120, 90, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def test_drops_small_image():
    mp = MediaPipeline(CFG)
    kept, reason = mp._quality_and_dedup(_png(50, 50))
    assert kept is None and reason == "too_small"


def test_drops_extreme_aspect():
    mp = MediaPipeline(CFG)
    kept, reason = mp._quality_and_dedup(_png(2000, 100))
    assert kept is None and reason == "bad_aspect"


def test_keeps_good_image():
    mp = MediaPipeline(CFG)
    kept, reason = mp._quality_and_dedup(_png(300, 300))
    assert reason is None and kept is not None
    assert kept.width == 300 and kept.ext == "png"


def test_exact_duplicate_dropped():
    mp = MediaPipeline(CFG)
    data = _png(300, 300)
    assert mp._quality_and_dedup(data)[0] is not None
    kept, reason = mp._quality_and_dedup(data)
    assert kept is None and reason == "duplicate"


def test_perceptual_near_duplicate_dropped():
    mp = MediaPipeline(CFG)
    # same image re-saved at different size -> different bytes, same look
    assert mp._quality_and_dedup(_png(300, 300))[0] is not None
    kept, reason = mp._quality_and_dedup(_png(320, 320))
    assert kept is None and reason == "duplicate"
