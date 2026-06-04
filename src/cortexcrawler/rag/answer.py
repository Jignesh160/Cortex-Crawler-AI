"""Answer synthesis (ARCHITECTURE_FINAL.md §4).

Builds a grounded, cited prompt from retrieved chunks. Two backends:
  - local  : no LLM call; returns the assembled context + citations (offline default).
  - bedrock: Amazon Nova Lite (multimodal) generates the final answer.

Either way the answer is grounded ONLY in retrieved chunks, each carrying source_url.
"""
from __future__ import annotations

from .store import Hit

_SYSTEM = (
    "You are a helpful assistant. Answer ONLY from the provided sources. "
    "If the answer is not in the sources, say you don't know. Cite sources by [n]."
)


def build_context(hits: list[Hit]) -> tuple[str, list[str]]:
    blocks, citations = [], []
    for i, h in enumerate(hits, 1):
        md = h.metadata
        src = md.get("source_url", "")
        citations.append(f"[{i}] {md.get('title','')} — {src}")
        tag = "IMAGE" if md.get("modality") == "image" else "TEXT"
        snippet = md.get("text", "")
        if md.get("modality") == "image":
            snippet = f"(image: {md.get('image_url','')}) {snippet}"
        blocks.append(f"[{i}] ({tag}) {md.get('section_path','')}\n{snippet}")
    return "\n\n".join(blocks), citations


def answer_local(query: str, hits: list[Hit]) -> str:
    context, citations = build_context(hits)
    return (
        f"Q: {query}\n\n"
        f"Top sources (no LLM call — offline mode):\n{context}\n\n"
        f"Citations:\n" + "\n".join(citations)
    )


def answer_bedrock(query: str, hits: list[Hit], model_id: str = "amazon.nova-lite-v1:0",
                   region: str | None = None) -> str:
    import json
    import boto3

    from ..retry import with_retry

    context, citations = build_context(hits)
    rt = boto3.client("bedrock-runtime", region_name=region)
    prompt = f"Sources:\n{context}\n\nQuestion: {query}"
    body = {
        "system": [{"text": _SYSTEM}],
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": 600, "temperature": 0.2},
    }

    @with_retry(attempts=4)
    def call() -> dict:
        resp = rt.invoke_model(modelId=model_id, body=json.dumps(body))
        return json.loads(resp["body"].read())

    payload = call()
    text = payload["output"]["message"]["content"][0]["text"]
    return text + "\n\nCitations:\n" + "\n".join(citations)


def answer(query: str, hits: list[Hit], cfg: dict) -> str:
    if (cfg or {}).get("backend") == "bedrock":
        return answer_bedrock(query, hits,
                              model_id=cfg.get("model_id", "amazon.nova-lite-v1:0"),
                              region=cfg.get("region"))
    return answer_local(query, hits)
