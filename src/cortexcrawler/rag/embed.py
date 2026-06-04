"""Embedders (ARCHITECTURE_FINAL.md §4).

One interface, two implementations selected by config — "models are config, not code":

  - LocalEmbedder   : hashed bag-of-words, zero deps beyond numpy. Dev/offline default
                      so the whole pipeline runs without AWS. NOT production quality.
  - BedrockEmbedder : Amazon Titan Multimodal Embeddings (text + image). Production.

Both return L2-normalized float32 vectors, so cosine == dot product downstream.
"""
from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

_TOKEN = re.compile(r"\w+")


class Embedder(Protocol):
    dim: int
    def embed_text(self, text: str) -> np.ndarray: ...
    def embed_image(self, image_bytes: bytes, alt: str = "") -> np.ndarray: ...


def _l2(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


class LocalEmbedder:
    """Deterministic hashed-ngram embedding. Good enough to prove retrieval offline."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _hash_vec(self, tokens: list[str]) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            v[idx] += sign
        return _l2(v)

    def embed_text(self, text: str) -> np.ndarray:
        toks = _TOKEN.findall(text.lower())
        # add bigrams for a little phrase sensitivity
        bigrams = [f"{toks[i]}_{toks[i+1]}" for i in range(len(toks) - 1)]
        return self._hash_vec(toks + bigrams)

    def embed_image(self, image_bytes: bytes, alt: str = "") -> np.ndarray:
        # Local mode can't see pixels; embed the alt text as a stand-in.
        return self.embed_text(alt or "image")


class BedrockEmbedder:
    """Amazon Titan Multimodal Embeddings via Bedrock. Requires boto3 + AWS creds."""

    def __init__(self, model_id: str = "amazon.titan-embed-image-v1",
                 region: str | None = None, dim: int = 1024):
        import boto3  # lazy import so local mode needs no boto3
        self.dim = dim
        self.model_id = model_id
        self._rt = boto3.client("bedrock-runtime", region_name=region)

    def _invoke(self, body: dict) -> np.ndarray:
        import json

        from ..retry import with_retry

        @with_retry(attempts=4)
        def call() -> dict:
            resp = self._rt.invoke_model(modelId=self.model_id, body=json.dumps(body))
            return json.loads(resp["body"].read())

        payload = call()
        return _l2(np.asarray(payload["embedding"], dtype=np.float32))

    def embed_text(self, text: str) -> np.ndarray:
        return self._invoke({"inputText": text, "embeddingConfig": {"outputEmbeddingLength": self.dim}})

    def embed_image(self, image_bytes: bytes, alt: str = "") -> np.ndarray:
        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        body: dict = {"inputImage": b64, "embeddingConfig": {"outputEmbeddingLength": self.dim}}
        if alt:
            body["inputText"] = alt
        return self._invoke(body)


def get_embedder(cfg: dict) -> Embedder:
    backend = (cfg or {}).get("backend", "local")
    if backend == "bedrock":
        return BedrockEmbedder(
            model_id=cfg.get("model_id", "amazon.titan-embed-image-v1"),
            region=cfg.get("region"),
            dim=cfg.get("dim", 1024),
        )
    return LocalEmbedder(dim=cfg.get("dim", 512))
