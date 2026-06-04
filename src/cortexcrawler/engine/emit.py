"""Emit layer — THE SEAM (ARCHITECTURE_FINAL.md §6).

Writes one .md per page with YAML front-matter, plus content-addressed image files
and per-image sidecar JSON. This file format IS the contract the rag/ layer and the
chatbot consume. Locally we mirror the future S3 layout under knowledge/.

  knowledge/<site>/<slug>.md
  knowledge/<site>/images/<sha256>.<ext>
  knowledge/<site>/images/<sha256>.json
"""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from slugify import slugify

from .media import KeptImage


@dataclass
class PageRecord:
    source_url: str
    title: str
    fetched_at: str
    content_hash: str
    section_path: str = ""
    lang: str = "en"
    status: str = "ok"          # ok | partial | empty
    crawl_depth: int = 0
    images: list[dict] = field(default_factory=list)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _image_title(src) -> str:
    """Best available title for an image: alt -> caption -> surrounding text."""
    for cand in (src.alt, src.caption):
        c = (cand or "").strip()
        if c:
            return c
    st = (src.surrounding_text or "").strip()
    if st:
        snippet = st[:80]
        if len(st) > 80:
            snippet = snippet.rsplit(" ", 1)[0] + "…"
        return snippet
    return "image"


def _site_dir(url: str) -> str:
    return urlsplit(url).netloc.replace(":", "_")


def _slug_for(url: str, title: str) -> str:
    path = urlsplit(url).path.strip("/")
    base = path or title or "index"
    slug = slugify(base)[:80] or "index"
    return slug


class Emitter:
    def __init__(self, root: str, image_base_url: str = ""):
        self.root = Path(root)
        self.image_base_url = image_base_url.rstrip("/")

    def _image_ref(self, site: str, img: KeptImage) -> str:
        """URL used inside the markdown. S3/CloudFront base if configured, else relative."""
        filename = f"{img.image_id}.{img.ext}"
        if self.image_base_url:
            return f"{self.image_base_url}/{site}/images/{filename}"
        return f"images/{filename}"

    def write_page(
        self,
        url: str,
        title: str,
        lang: str,
        markdown: str,
        content_hash: str,
        kept_images: list[KeptImage],
        status: str = "ok",
        depth: int = 0,
    ) -> Path:
        site = _site_dir(url)
        site_dir = self.root / site
        img_dir = site_dir / "images"
        site_dir.mkdir(parents=True, exist_ok=True)
        if kept_images:
            img_dir.mkdir(parents=True, exist_ok=True)

        # Write images + sidecars; build a reference + appendix.
        image_meta: list[dict] = []
        appendix_lines: list[str] = []
        for img in kept_images:
            fpath = img_dir / f"{img.image_id}.{img.ext}"
            if not fpath.exists():
                fpath.write_bytes(img.data)
            ref = self._image_ref(site, img)
            sidecar = {
                "image_id": img.image_id,
                "s3_url": ref,
                "page_url": url,
                "src_url": img.src.src_url,
                "alt": img.src.alt,
                "caption": img.src.caption,
                "surrounding_text": img.src.surrounding_text,
                "width": img.width,
                "height": img.height,
                "phash": img.phash,
                "status": "kept",
                "drop_reason": None,
            }
            (img_dir / f"{img.image_id}.json").write_text(
                json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            label = _image_title(img.src)
            image_meta.append({"image_id": img.image_id, "url": ref, "alt": label})
            appendix_lines.append(f"![{label}]({ref})")

        record = PageRecord(
            source_url=url,
            title=title,
            fetched_at=_now(),
            content_hash=content_hash,
            lang=lang or "en",
            status=status,
            crawl_depth=depth,
            images=image_meta,
        )

        front = yaml.safe_dump(asdict(record), sort_keys=False, allow_unicode=True).strip()
        body = markdown.strip()
        if appendix_lines:
            body += "\n\n## Images\n\n" + "\n\n".join(appendix_lines)
        doc = f"---\n{front}\n---\n\n# {title}\n\n{body}\n"

        out = site_dir / f"{_slug_for(url, title)}.md"
        out.write_text(doc, encoding="utf-8")
        return out
