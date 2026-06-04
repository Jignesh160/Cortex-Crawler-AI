"""Text dedup (ARCHITECTURE_FINAL.md §5).

Tier 1 exact: sha256 of normalized text.
Tier 2 near-dup: MinHash (Jaccard over word shingles) across pages.
(Tier 3 semantic dedup happens later in the rag/ layer with embeddings.)
"""
from __future__ import annotations

import hashlib
import re

from datasketch import MinHash, MinHashLSH

_TOKEN = re.compile(r"\w+")


def content_hash(text: str) -> str:
    norm = " ".join(_TOKEN.findall(text.lower()))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def shingles(text: str, k: int = 5) -> set[str]:
    """Word k-shingles for Jaccard similarity."""
    tokens = _TOKEN.findall(text.lower())
    if len(tokens) < k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class NearDupFilter:
    """Intra-document near-duplicate filter (keep first, drop later near-dups).

    Used WITHIN a single page so the same content block (e.g. specs rendered both
    as flattened text and as a table) isn't emitted twice. Stateless across pages:
    construct a fresh filter per page.
    """

    def __init__(self, threshold: float = 0.9, shingle_k: int = 5):
        self.threshold = threshold
        self.k = shingle_k
        self._seen: list[set[str]] = []

    def is_duplicate(self, text: str) -> bool:
        sh = shingles(text, self.k)
        for prev in self._seen:
            if jaccard(sh, prev) > self.threshold:
                return True
        self._seen.append(sh)
        return False


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
