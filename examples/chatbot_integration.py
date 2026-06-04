"""How to integrate CortexCrawler into an existing chatbot.

Credentials: NONE are passed here. boto3 inherits them from the chatbot's host
process (env vars / IAM role / instance profile) — the same AWS setup your chatbot
already uses for AI.

Two integration styles below. Style A (recommended for you) uses CortexCrawler for
retrieval only and lets YOUR existing chatbot model write the answer.
"""
from cortexcrawler import KnowledgeBase

# Point at your S3 Vectors bucket/index. Region optional (defaults to AWS_REGION).
kb = KnowledgeBase.for_aws(bucket="cortexcrawler-kb", index="cortex-kb", region="us-east-1")


# ---------------------------------------------------------------------------
# One-time / scheduled: build or refresh the knowledge base from your sites.
# ---------------------------------------------------------------------------
def refresh_knowledge_base(urls: list[str]) -> None:
    for url in urls:
        kb.crawl(url)          # -> knowledge/*.md + images
    stats = kb.index()         # -> Titan embeddings -> S3 Vectors
    print("indexed:", stats)


# ---------------------------------------------------------------------------
# Style A (recommended): retrieval only -> feed chunks to YOUR chatbot model.
# ---------------------------------------------------------------------------
def build_rag_context(user_message: str, k: int = 5) -> tuple[str, list[str]]:
    """Return (context_block, citations) to prepend to your chatbot's prompt."""
    hits = kb.search(user_message, top_k=k)
    blocks, citations = [], []
    for i, h in enumerate(hits, 1):
        md = h.metadata
        citations.append(f"[{i}] {md.get('title','')} — {md.get('source_url','')}")
        snippet = md.get("text", "")
        if md.get("modality") == "image":
            snippet = f"(image: {md.get('image_url','')}) {snippet}"
        blocks.append(f"[{i}] {snippet}")
    return "\n\n".join(blocks), citations


def chatbot_reply(user_message: str) -> str:
    context, citations = build_rag_context(user_message)
    # --- hand off to YOUR existing model (pseudo-code) ---
    # prompt = f"Use these sources to answer.\n\n{context}\n\nUser: {user_message}"
    # answer = your_existing_llm(prompt)
    # return answer + "\n\nSources:\n" + "\n".join(citations)
    return context  # placeholder


# ---------------------------------------------------------------------------
# Style B: let CortexCrawler answer with Amazon Nova (no extra model wiring).
# ---------------------------------------------------------------------------
def chatbot_reply_with_nova(user_message: str) -> str:
    kb_nova = KnowledgeBase.for_aws(
        bucket="cortexcrawler-kb", index="cortex-kb",
        region="us-east-1", answer_with_nova=True,
    )
    return kb_nova.ask(user_message, top_k=5)


if __name__ == "__main__":
    print(chatbot_reply_with_nova("what mystery books are available?"))
