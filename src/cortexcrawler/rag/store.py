"""Vector stores (ARCHITECTURE_FINAL.md §8).

One interface, two backends selected by config:

  - LocalVectorStore : numpy + on-disk .npz/.json. Runs anywhere, no AWS. Dev default.
  - S3VectorStore    : Amazon S3 Vectors via boto3. Production.

Records carry full metadata (provenance) so retrieval results are citable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np


@dataclass
class Record:
    id: str
    vector: np.ndarray
    metadata: dict = field(default_factory=dict)


@dataclass
class Hit:
    id: str
    score: float
    metadata: dict


class VectorStore(Protocol):
    def upsert(self, records: list[Record]) -> int: ...
    def query(self, vector: np.ndarray, top_k: int = 5,
              modality: str | None = None) -> list[Hit]: ...
    def all_vectors(self) -> np.ndarray: ...
    def save(self) -> None: ...


class LocalVectorStore:
    def __init__(self, path: str = "index/local_store"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._ids: list[str] = []
        self._meta: list[dict] = []
        self._vecs: list[np.ndarray] = []
        self._id_set: set[str] = set()
        self._load()

    def _load(self) -> None:
        vpath, mpath = self.path / "vectors.npz", self.path / "meta.json"
        if vpath.exists() and mpath.exists():
            data = np.load(vpath)
            mat = data["vectors"]
            meta = json.loads(mpath.read_text(encoding="utf-8"))
            self._ids = meta["ids"]
            self._meta = meta["meta"]
            self._vecs = [mat[i] for i in range(mat.shape[0])]
            self._id_set = set(self._ids)

    def upsert(self, records: list[Record]) -> int:
        added = 0
        for r in records:
            if r.id in self._id_set:
                continue
            self._ids.append(r.id)
            self._meta.append(r.metadata)
            self._vecs.append(r.vector.astype(np.float32))
            self._id_set.add(r.id)
            added += 1
        return added

    def all_vectors(self) -> np.ndarray:
        if not self._vecs:
            return np.zeros((0, 0), dtype=np.float32)
        return np.vstack(self._vecs)

    def query(self, vector: np.ndarray, top_k: int = 5,
              modality: str | None = None) -> list[Hit]:
        if not self._vecs:
            return []
        mat = self.all_vectors()
        sims = mat @ vector.astype(np.float32)  # cosine (all L2-normalized)
        order = np.argsort(-sims)
        hits: list[Hit] = []
        for i in order:
            md = self._meta[i]
            if modality and md.get("modality") != modality:
                continue
            hits.append(Hit(id=self._ids[i], score=float(sims[i]), metadata=md))
            if len(hits) >= top_k:
                break
        return hits

    def save(self) -> None:
        np.savez_compressed(self.path / "vectors.npz", vectors=self.all_vectors())
        (self.path / "meta.json").write_text(
            json.dumps({"ids": self._ids, "meta": self._meta}, ensure_ascii=False),
            encoding="utf-8",
        )


class S3VectorStore:
    """Amazon S3 Vectors. Skeleton wired to the same interface; needs boto3 + AWS.

    Fill in bucket/index names from config when you go live. The contract (upsert /
    query / metadata) is identical to LocalVectorStore, so swapping is config-only.
    """

    # 'text' can be up to 1000 chars; keep big/free-text fields non-filterable.
    NON_FILTERABLE = ["text", "image_url"]
    _PUT_BATCH = 200  # stay well under API limits

    def __init__(self, bucket: str, index: str, region: str | None = None,
                 dim: int = 1024, distance_metric: str = "cosine"):
        import boto3
        self._client = boto3.client("s3vectors", region_name=region)
        self.bucket = bucket
        self.index = index
        self.dim = dim
        self.distance_metric = distance_metric

    def ensure(self) -> None:
        """Create the vector bucket + index if they don't already exist (idempotent)."""
        try:
            self._client.get_vector_bucket(vectorBucketName=self.bucket)
        except self._client.exceptions.NotFoundException:
            self._client.create_vector_bucket(vectorBucketName=self.bucket)
        try:
            self._client.get_index(vectorBucketName=self.bucket, indexName=self.index)
        except self._client.exceptions.NotFoundException:
            self._client.create_index(
                vectorBucketName=self.bucket, indexName=self.index,
                dataType="float32", dimension=self.dim,
                distanceMetric=self.distance_metric,
                metadataConfiguration={"nonFilterableMetadataKeys": self.NON_FILTERABLE},
            )

    def upsert(self, records: list[Record]) -> int:
        total = 0
        for i in range(0, len(records), self._PUT_BATCH):
            batch = records[i:i + self._PUT_BATCH]
            vectors = [
                {"key": r.id,
                 "data": {"float32": r.vector.astype(np.float32).tolist()},
                 "metadata": r.metadata}
                for r in batch
            ]
            self._client.put_vectors(vectorBucketName=self.bucket,
                                     indexName=self.index, vectors=vectors)
            total += len(vectors)
        return total

    def query(self, vector: np.ndarray, top_k: int = 5,
              modality: str | None = None) -> list[Hit]:
        kwargs: dict = dict(
            vectorBucketName=self.bucket, indexName=self.index,
            queryVector={"float32": vector.astype(np.float32).tolist()},
            topK=top_k, returnMetadata=True, returnDistance=True,
        )
        if modality:
            kwargs["filter"] = {"modality": modality}
        resp = self._client.query_vectors(**kwargs)
        out: list[Hit] = []
        for v in resp.get("vectors", []):
            dist = float(v.get("distance", 0.0))
            # Convert cosine distance -> similarity so scores match LocalVectorStore.
            score = 1.0 - dist if self.distance_metric == "cosine" else -dist
            out.append(Hit(id=v["key"], score=score, metadata=v.get("metadata", {})))
        return out

    def all_vectors(self) -> np.ndarray:
        raise NotImplementedError("S3 Vectors does not bulk-export; not needed at query time")

    def save(self) -> None:
        pass  # S3 Vectors persists server-side


def get_store(cfg: dict) -> VectorStore:
    backend = (cfg or {}).get("backend", "local")
    if backend == "s3vectors":
        store = S3VectorStore(
            bucket=cfg["bucket"], index=cfg["index"], region=cfg.get("region"),
            dim=cfg.get("dim", 1024), distance_metric=cfg.get("distance_metric", "cosine"),
        )
        store.ensure()  # create bucket + index on first use
        return store
    return LocalVectorStore(path=cfg.get("path", "index/local_store"))
