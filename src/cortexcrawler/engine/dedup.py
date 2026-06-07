"""Cross-page text dedup.

Tier 1 exact: sha256 of normalized text.
Tier 2 near-dup: MinHash (Jaccard over word shingles) across pages.
"""
from __future__ import annotations

import hashlib
import re

from datasketch import MinHash, MinHashLSH

_TOKEN = re.compile(r"\w+")


def content_hash(text: str) -> str:
    norm = " ".join(_TOKEN.findall(text.lower()))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    tokens = _TOKEN.findall(text.lower())
    # 5-word shingles capture phrasing better than single tokens.
    shingles = {" ".join(tokens[i:i + 5]) for i in range(max(1, len(tokens) - 4))}
    for sh in shingles:
        m.update(sh.encode("utf-8"))
    return m


class TextDedup:
    def __init__(self, enabled: bool, threshold: float):
        self.enabled = enabled
        self._exact: set[str] = set()
        self._lsh = MinHashLSH(threshold=threshold, num_perm=128) if enabled else None
        self._n = 0

    def is_duplicate(self, text: str) -> bool:
        h = content_hash(text)
        if h in self._exact:
            return True
        if self.enabled and self._lsh is not None and text.strip():
            mh = _minhash(text)
            if self._lsh.query(mh):
                return True
            self._lsh.insert(f"doc-{self._n}", mh)
        self._exact.add(h)
        self._n += 1
        return False
