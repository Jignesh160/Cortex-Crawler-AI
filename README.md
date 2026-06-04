# CortexCrawler AI

Multimodal RAG knowledge-base builder. Crawls a few known sites, extracts **text +
images**, and produces clean, deduplicated **markdown** that a chatbot ingests
directly. See [ARCHITECTURE_FINAL.md](ARCHITECTURE_FINAL.md) for the full design.

Installable Python package (`cortexcrawler`). Runs anywhere with built-in defaults
(no AWS required); flip to Amazon Bedrock + S3 Vectors via config when you go live.

## Install

```bash
pip install "git+https://github.com/Jignesh160/Context-Crawler-AI.git"
# optional extras:
pip install "cortexcrawler[aws]"      # Bedrock Titan/Nova + S3 Vectors
pip install "cortexcrawler[dynamic]"  # Playwright for JS-heavy sites
```

## Use from your chatbot (the public API)

```python
from cortexcrawler import KnowledgeBase

kb = KnowledgeBase()                  # built-in defaults; or KnowledgeBase(config=load_config("my.yaml"))
kb.crawl("https://your-site.com/")    # site -> knowledge/*.md + images
kb.index()                            # knowledge/ -> vector index

answer = kb.ask("How do I reset my password?")   # grounded, cited answer
hits   = kb.search("password reset", top_k=5)     # raw citable chunks
```

That's the whole surface your chatbot needs. Everything else is internal.

## CLI (same operations)

```bash
cortex-crawl "https://your-site.com/" --max-pages 20 --max-depth 2
cortex-index
cortex-ask "your question" --top-k 5
```

Output lands under `knowledge/<site>/`:

```
knowledge/<site>/<slug>.md              # text in markdown + image refs + front-matter
knowledge/<site>/images/<sha256>.jpg    # kept images, content-addressed
knowledge/<site>/images/<sha256>.json   # per-image provenance sidecar
```

All knobs live in [config/settings.yaml](config/settings.yaml) (rate limit, depth,
image size/aspect gates, dedup thresholds). Nothing is hardcoded.

### What Phase 1 guarantees

| Guarantee | How |
|-----------|-----|
| Polite & legal | robots.txt obeyed, per-domain rate limit, honest User-Agent |
| Clean text | trafilatura extraction → markdown; thin pages flagged `partial` |
| **No junk images** | quality gate: size / aspect / byte-size / type |
| **No duplicates** | text: sha256 + MinHash · images: sha256 + **perceptual hash**, across all pages |
| Grounded | every page + image carries `source_url` provenance for citations |
| Swappable engine | downstream reads `.md` files only — never engine internals |

## Phase 2 (built) — RAG layer

Reads `knowledge/**/*.md` (never `engine/`) and builds a retrievable, citable index.
**Runs locally with no AWS** — every cloud piece sits behind an interface with a local
default, so you can verify the whole pipeline today and flip to AWS via config.

### Build the index, then ask

```bash
cortex-index
cortex-ask "books about history and war" --top-k 3
cortex-ask "a mystery novel cover" --modality image
```

### `rag/` modules

| Module | Does | Local default | Production (config switch) |
|--------|------|---------------|----------------------------|
| `chunk.py` | heading-aware chunking + image chunks, with provenance | — | — |
| `embed.py` | text + image embeddings | hashed bag-of-words | **Titan Multimodal** (Bedrock) |
| `semantic_dedup.py` | Tier-3 semantic dedup gate before insert | cosine threshold | same |
| `store.py` | vector upsert + similarity search | numpy `.npz` on disk | **Amazon S3 Vectors** |
| `retrieve.py` | query → embed → search (modality filter) | — | — |
| `answer.py` | grounded, cited answer | assembled context | **Amazon Nova Lite** |

## Configuration

Built-in defaults work out of the box. Override via (increasing precedence):
1. `config/settings.yaml` in the working dir (or `$CORTEX_CONFIG`)
2. environment variables — `CORTEX_EMBEDDER_BACKEND`, `CORTEX_STORE_BACKEND`,
   `CORTEX_ANSWER_BACKEND`, `CORTEX_VECTOR_BUCKET`, `CORTEX_VECTOR_INDEX`,
   `AWS_REGION`, `CORTEX_IMAGE_BASE_URL`, `CORTEX_LOG_LEVEL`

### Flip to AWS (config only, no code change)

Set `embedder.backend: bedrock` (Titan), `store.backend: s3vectors` (bucket+index),
`answer.backend: bedrock` (Nova Lite). Requires `pip install "cortexcrawler[aws]"` +
AWS creds. Because vectors derive from the markdown, switching is just a re-index —
never a re-crawl.

## Project layout

```
src/cortexcrawler/
  engine/    in-house crawler (fetch, politeness, extract, media, dedup, emit, crawl)
  rag/       RAG layer (chunk, embed, store, semantic_dedup, index, retrieve, answer)
  api.py     KnowledgeBase — the public API your chatbot imports
  cli.py     console entry points: cortex-crawl / cortex-index / cortex-ask
  log.py     logging · retry.py  retry/backoff
knowledge/   SOURCE OF TRUTH — markdown + images (rebuildable index derives from this)
index/       generated vector index (local_store) — rebuildable from knowledge/
config/      optional settings.yaml (defaults are built in)
tests/       pytest suite
```

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check src tests
```
