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

    def __init__(self, bucket: str, index: str, region: str | None = None):
        import boto3
        self._client = boto3.client("s3vectors", region_name=region)
        self.bucket = bucket
        self.index = index

    def upsert(self, records: list[Record]) -> int:
        vectors = [
            {"key": r.id,
             "data": {"float32": r.vector.astype(np.float32).tolist()},
             "metadata": r.metadata}
            for r in records
        ]
        # Batched put_vectors; chunk to API limits in production.
        self._client.put_vectors(vectorBucketName=self.bucket,
                                  indexName=self.index, vectors=vectors)
        return len(vectors)

    def query(self, vector: np.ndarray, top_k: int = 5,
              modality: str | None = None) -> list[Hit]:
        flt = {"modality": modality} if modality else None
        resp = self._client.query_vectors(
            vectorBucketName=self.bucket, indexName=self.index,
            queryVector={"float32": vector.astype(np.float32).tolist()},
            topK=top_k, returnMetadata=True,
            **({"filter": flt} if flt else {}),
        )
        return [Hit(id=v["key"], score=float(v.get("distance", 0.0)),
                    metadata=v.get("metadata", {})) for v in resp.get("vectors", [])]

    def all_vectors(self) -> np.ndarray:
        raise NotImplementedError("S3 Vectors does not bulk-export; not needed at query time")

    def save(self) -> None:
        pass  # S3 Vectors persists server-side


def get_store(cfg: dict) -> VectorStore:
    backend = (cfg or {}).get("backend", "local")
    if backend == "s3vectors":
        return S3VectorStore(bucket=cfg["bucket"], index=cfg["index"], region=cfg.get("region"))
    return LocalVectorStore(path=cfg.get("path", "index/local_store"))
