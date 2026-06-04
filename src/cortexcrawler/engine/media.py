"""Image media pipeline (ARCHITECTURE_FINAL.md §5).

For every discovered image: download -> decode -> QUALITY GATE (drop chrome) ->
DEDUP (sha256 exact + pHash near-dup). Only survivors are written to disk and
referenced from the markdown. The clean-database guarantee starts here.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import imagehash
from PIL import Image

from .extract import DiscoveredImage
from .fetch import Fetcher

_EXT_BY_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}


@dataclass
class KeptImage:
    image_id: str          # sha256 of bytes
    ext: str
    data: bytes
    width: int
    height: int
    phash: str
    src: DiscoveredImage


@dataclass
class ImageVerdict:
    kept: KeptImage | None
    drop_reason: str | None  # chrome | too_small | bad_aspect | too_few_bytes | bad_type | duplicate | decode_error


class MediaPipeline:
    """Stateful across a crawl run so dedup spans all pages."""

    def __init__(self, cfg: dict):
        self.min_w = cfg.get("min_width", 100)
        self.min_h = cfg.get("min_height", 100)
        self.max_aspect = cfg.get("max_aspect_ratio", 10.0)
        self.min_bytes = cfg.get("min_bytes", 2048)
        self.allowed = {t.lower() for t in cfg.get("allowed_types", [])}
        self.phash_threshold = cfg.get("phash_hamming_threshold", 6)

        self._seen_sha: set[str] = set()
        self._seen_phash: list[imagehash.ImageHash] = []

    def _quality_and_dedup(self, data: bytes) -> tuple[KeptImage | None, str | None]:
        # R1 info gate: tiny payloads are almost always chrome/spacers.
        if len(data) < self.min_bytes:
            return None, "too_few_bytes"

        # Exact dedup before we even decode (cheap).
        sha = hashlib.sha256(data).hexdigest()
        if sha in self._seen_sha:
            return None, "duplicate"

        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception:
            return None, "decode_error"

        fmt = (img.format or "").upper()
        ext = _EXT_BY_FORMAT.get(fmt)
        if ext is None or (self.allowed and ext not in self.allowed and fmt.lower() not in self.allowed):
            return None, "bad_type"

        w, h = img.size
        # R0 size gate.
        if w < self.min_w or h < self.min_h:
            return None, "too_small"
        # R0 aspect gate (banners, dividers, rules).
        long_side, short_side = max(w, h), max(1, min(w, h))
        if long_side / short_side > self.max_aspect:
            return None, "bad_aspect"

        # Near-dup gate: perceptual hash catches resized / re-saved copies that
        # sha256 misses.
        ph = imagehash.phash(img.convert("RGB"))
        for seen in self._seen_phash:
            if (ph - seen) <= self.phash_threshold:
                return None, "duplicate"

        self._seen_sha.add(sha)
        self._seen_phash.append(ph)
        return (
            KeptImage(image_id=sha, ext=ext, data=data, width=w, height=h,
                      phash=str(ph), src=DiscoveredImage("", "", "", "")),
            None,
        )

    def process(self, fetcher: Fetcher, disc: DiscoveredImage) -> ImageVerdict:
        got = fetcher.fetch_bytes(disc.src_url)
        if got is None:
            return ImageVerdict(None, "fetch_failed")
        data, _ctype = got
        kept, reason = self._quality_and_dedup(data)
        if kept is None:
            return ImageVerdict(None, reason)
        kept.src = disc
        return ImageVerdict(kept, None)
