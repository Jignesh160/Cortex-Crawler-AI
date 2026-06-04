"""Semantic dedup — Tier 3 gate (ARCHITECTURE_FINAL.md §5).

Sits in front of the vector store: a candidate is dropped if its embedding is within
`threshold` cosine of something already accepted. Catches paraphrased text and
re-rendered images that exact + near-dup (handled in engine/) miss.
"""
from __future__ import annotations

import numpy as np


class SemanticDedup:
    def __init__(self, threshold: float = 0.97):
        self.threshold = threshold
        self._accepted: list[np.ndarray] = []

    def is_duplicate(self, vector: np.ndarray) -> bool:
        if self._accepted:
            mat = np.vstack(self._accepted)
            sims = mat @ vector.astype(np.float32)
            if float(sims.max()) >= self.threshold:
                return True
        self._accepted.append(vector.astype(np.float32))
        return False
