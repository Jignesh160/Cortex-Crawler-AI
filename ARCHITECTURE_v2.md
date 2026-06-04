# CortexCrawler AI — Architecture v2 (Upgraded)

> Revision of the original *CortexCrawler AI* design. Same vision — a semantic
> web-extraction and dataset-generation platform — but re-engineered for **cost
> control, correctness, legal safety, and phased delivery**. Nothing here is built
> yet; this is the target design.

---

## 0. Your profile — RAG knowledge base from a few known sites

> **This is the scope you're actually building for.** It overrides the general
> design below: read this first, treat §1–§9 as the broader reference you can grow
> into later.

**What you're doing:** crawl a small set of known/permitted sites → clean → chunk →
embed → store, so a chatbot **retrieves** real source chunks at query time. You are
**not** generating conversational training data, and you are **not** crawling the
open web.

**What this means — the design collapses to a much smaller system:**

| Drop entirely (for now) | Keep — and make excellent | Why |
|-------------------------|---------------------------|-----|
| LLM dataset *generation* (QA/ChatML) | Cleaned, well-bounded **chunks** | RAG retrieves originals; it doesn't invent answers |
| Distributed crawl frontier, proxies, autonomous agents | A simple per-site crawl | A handful of known sites needs none of it |
| Qdrant cluster, Mongo, Celery (early) | One vector store + Postgres + files | Right-size to a few sites |
| Tiered relevance T2 (LLM) | T0/T1 cheap filtering | You're keeping most content from trusted sites |

**The three things that decide whether your RAG bot is good:**

1. **Chunking quality.** Retrieval is only as good as your chunk boundaries.
   Heading-aware + semantic boundaries, target ~300–800 tokens with small overlap,
   never split mid-table/mid-list. This is your #1 lever.
2. **Provenance on every chunk.** `source_url` + `title` + `section` + `fetched_at`
   so the chatbot can **cite** and you can refresh stale content. Non-negotiable.
3. **Embedding + retrieval setup.** BGE-M3 embeddings, store the chunk text *with*
   its metadata, and plan for hybrid (keyword + vector) retrieval — it noticeably
   beats pure vector search on factual lookups.

**A right-sized RAG pipeline for you:**

```
 few known URLs / sitemaps
      ▼
 robots.txt + polite rate-limit            (still do this)
      ▼
 Static fetch (httpx) → Playwright only if a site is JS-heavy
      ▼
 Trafilatura extraction → MARKDOWN (+ BS4 fallback)   ← keep tables, headings, lists
      ▼
 Cheap junk removal (nav/footer/cookie banners)
      ▼
 MinHash dedup (drop repeated boilerplate across pages)
      ▼
 ⭐ Store as .md files (canonical knowledge base)   ← YAML front-matter = provenance
      ▼
 Heading-aware + semantic CHUNKING (split on the markdown headings)
      ▼
 BGE-M3 embeddings (cached by content hash)
      ▼
 Semantic dedup (cosine) — optional, light
      ▼
 PII scrubbing (only if sites contain personal data)
      ▼
 Vector store + Postgres metadata  → chatbot retrieves at query time
```

### Markdown as the canonical content store

Cleaned content is stored as **one `.md` file per page**, with provenance in YAML
front-matter. The vector store/DB is then just a *derived index* — the markdown
files are the source of truth (readable, git-versionable, re-embeddable any time).

```
datasets/
  <site>/
    <slug>.md
```

```markdown
---
source_url: https://example.com/docs/intro
title: Introduction
fetched_at: 2026-06-04T12:00:00Z
content_hash: sha256:…
section_path: Docs > Getting Started > Introduction
lang: en
---

# Introduction

Body content in clean markdown — headings, lists and tables preserved so the
chunker can split on `#`/`##` boundaries…
```

**Why this is the right move for your RAG case:**
- **Headings survive** → heading-aware chunking becomes trivial (split on `#`/`##`).
- **Provenance travels with content** → front-matter carries `source_url` for citations.
- **Git-versionable** → diff what changed between re-crawls; DVC optional on top.
- **Re-embeddable** → swap embedding models later without re-crawling.
- Trafilatura can emit markdown directly (`output_format="markdown"`).

**Pipeline order note:** markdown is stored *before* chunking/embedding. Chunks and
vectors are rebuildable from the `.md` files at any time; the files are what you keep.

---

## 0B. Build decision — your own Crawl4AI-style engine

> **Chosen approach:** build the crawl + extraction + markdown engine *yourself*
> (a Crawl4AI-style tool), rather than depending on Crawl4AI. Full control, no
> upstream dependency, deep understanding of every layer.

**Guiding rule: own the orchestration, reuse the primitives.** Do not reimplement a
browser, an HTML parser, or a markdown serializer from scratch — Crawl4AI itself
stands on Playwright + lxml. Your value is the *orchestration and the filtering
intelligence*, not the low-level plumbing.

### Engine modules (what you build vs what you stand on)

| Module | You build | Stand on |
|--------|-----------|----------|
| Fetch dispatcher (static vs JS auto-detect) | Routing logic | httpx (static) + Playwright (dynamic) |
| Browser pool / sessions | Pooling, reuse, concurrency caps | Playwright contexts |
| HTML → clean markdown ("fit markdown") | Noise-filtering logic | lxml / selectolax + markdownify; Trafilatura as reference |
| Content filters (pruning threshold, BM25 query) | **Core IP** — relevance scoring | rank-bm25 for the math |
| Deep crawl (BFS / DFS / best-first) | Frontier scheduler, URL normalize+dedup, scope/depth | — |
| Politeness (robots, rate-limit, backoff, proxy) | Policy + per-domain limits | urllib.robotparser |
| Extraction strategies (CSS/XPath schema, LLM) | Pluggable strategy interface | Pydantic schemas; Bedrock for LLM extraction |
| Resumable state / checkpoints | Crash-recovery + resume | SQLite / JSON state file |
| Output layer (markdown + YAML front-matter + citations) | **Your provenance schema** | — |

### Honest scope warning

The front half (browser automation, JS rendering, HTML→markdown, deep-crawl
edge cases) is the fiddly, edge-case-heavy part — it's why a mature crawler has
years of commits. Budget for it. The RAG layer on top (Titan → vector store → Nova)
is the easy, high-value part.

### Suggested build order for the engine

1. **Static fetch + HTML→markdown + front-matter** on one page. (Prove the output.)
2. **Politeness**: robots.txt + per-domain rate limit + honest UA.
3. **Pruning content filter** (drop low-text-density nodes) → clean "fit markdown".
4. **Playwright fallback** for JS-heavy pages (auto-detect: retry in browser if
   static yield is too thin).
5. **Deep crawl**: frontier + URL dedup + BFS + scope/depth limits + resume state.
6. **BM25 query filter** (optional) for topic-focused crawls.
7. Hand off `.md` files to the **RAG layer** (Titan embeddings → vector store → Nova).

> Engine output stays exactly as §0 defines it: one `.md` file per page with YAML
> front-matter provenance. The engine is interchangeable — building your own changes
> *how* markdown is produced, not the contract downstream of it.

---

## 0C. Project structure & module contracts (the "good structure")

> A good structure = **a stable contract at every boundary**, so modules don't reach
> into each other's internals. Get this right and you can build piece by piece, swap
> your engine for Crawl4AI (or back), and bolt on the RAG layer with zero rework.
> The seam that makes it all work: **the `.md` file is the interface** between the
> crawler and everything downstream.

### Folder layout

```
contextcrawler/
├── engine/                  # your Crawl4AI-style crawler (Section 0B)
│   ├── fetch/               #   static (httpx) + dynamic (Playwright) dispatcher
│   ├── politeness/          #   robots, rate-limit, proxy, UA
│   ├── extract/             #   HTML → clean markdown ("fit markdown")
│   ├── filter/              #   pruning + BM25 relevance (core IP)
│   ├── crawl/               #   deep-crawl frontier (BFS/DFS), URL dedup, scope
│   ├── state/               #   resumable checkpoints
│   └── emit/                #   writes .md + YAML front-matter  ← THE SEAM
│
├── knowledge/               # the canonical store = the .md files
│   └── <site>/<slug>.md
│
├── rag/                     # the AWS layer — reads knowledge/, never the engine
│   ├── chunk/               #   heading-aware + semantic chunking
│   ├── embed/               #   Titan Text Embeddings V2 (Bedrock)
│   ├── index/               #   vector store upsert (pgvector / Qdrant)
│   ├── retrieve/            #   hybrid (BM25 + vector) search
│   └── answer/              #   Nova Lite, runtime answer synthesis
│
├── pipeline/                # orchestration: run crawl → index → serve
├── config/                  # site list, scope rules, thresholds, model IDs
└── tests/
```

### The contracts (boundaries that must stay stable)

**1. Crawler → Knowledge** *(the most important seam)*
The engine's ONLY output is a markdown file with this front-matter. Nothing
downstream may depend on anything else the engine does.

```yaml
---
source_url: string          # required — citation + re-crawl key
title: string               # required
fetched_at: iso8601         # required — freshness
content_hash: sha256        # required — dedup + change-detect + embed cache key
section_path: string        # optional — "Docs > Getting Started > Intro"
lang: string                # optional — default "en"
crawl_depth: int            # optional — provenance
status: ok | partial | empty
---
# clean markdown body
```

**2. Knowledge → RAG**
The RAG layer reads `knowledge/**/*.md` ONLY. It never imports from `engine/`.
This is what makes the engine swappable (your build ↔ Crawl4AI).
- Input: a markdown file (parsed front-matter + body).
- Output of chunking: `Chunk{ id, source_url, section_path, text, content_hash }`.

**3. Embed → Index**
- Input: `Chunk`. Output: `Vector{ chunk_id, embedding[1024], metadata }`.
- Embedding model ID lives in `config/`, never hardcoded — so Titan→BGE-M3 is a
  config change, not a code change.

**4. Retrieve → Answer**
- Input: user query. Output: ranked `Chunk[]` (with `source_url` for citations).
- The answer LLM (Nova Lite) receives chunks + query; model ID also from `config/`.

### Why this structure pays off

- **Engine is hot-swappable** — `rag/` reads files, so your crawler and Crawl4AI are
  interchangeable behind the same `.md` contract.
- **Models are config, not code** — Titan/Nova IDs in `config/`; swap to BGE-M3 or
  Nova Pro without touching logic.
- **Rebuildable index** — vectors derive from `.md` files; re-embed anytime.
- **Incremental build** — each folder is buildable and testable in isolation, in the
  order from §0B, because the contracts are fixed up front.

---

## 0D. Multimodal (text + images) + clean-database guarantee

> **Requirement:** capture **both text and images**, and guarantee the database
> contains **no duplicates and no unmeaningful content** — for *both* modalities.

### Unified embedding space (the AWS unlock)

Switch the embedder from Titan Text V2 to **Amazon Titan Multimodal Embeddings**
(`amazon.titan-embed-image-v1`). It embeds text *and* images into the **same vector
space**, so:
- a **text** query can retrieve a relevant **image** (diagram/chart) and vice versa,
- one vector store holds both modalities,
- **Nova Lite/Pro are multimodal**, so retrieved images can be passed to the answer LLM.

> Trade-off: Titan Text V2 is a bit stronger on *pure-text* retrieval. If text
> quality is critical you may run **two embedders** (Text V2 for text chunks,
> Multimodal for images) in two collections. Default for simplicity: **one
> multimodal space**. This is a `config/` choice, per §0C contract 3.

### What the engine emits now (extends the §0 contract)

The crawler still writes one `.md` per page, but now also:
- **extracts every `<img>`** with its `alt`, nearest caption, and surrounding text,
- **downloads** the image to object storage, named by `sha256`,
- references it in the markdown: `![alt](images/<sha256>.<ext>)`,
- writes a **sidecar image record** per kept image.

```yaml
# image record (one per kept image)
image_id: sha256
page_url: string            # where it was found (provenance)
src_url: string             # original image URL
alt: string
caption: string
surrounding_text: string    # context for retrieval + answer grounding
width: int
height: int
phash: string               # perceptual hash — near-dup detection
status: kept | dropped
drop_reason: null | chrome | too_small | duplicate | low_info
```

### Image quality gate — kill "unmeaningful" before the DB

Run cheap rules first, escalate only if needed:

| Tier | Check | Drops |
|------|-------|-------|
| R0 size | width/height < ~100px, or area below threshold | icons, spacers, tracking pixels |
| R0 aspect | extreme ratios (e.g. >10:1) | banners, dividers, rules |
| R0 type/role | logos/avatars/sprites by filename/role/CSS, SVG icons | UI chrome |
| R1 info | very low byte-size or low color entropy | blanks, solid fills |
| R2 (optional) vision | a vision check / CLIP-style "is this content?" | decorative stock imagery |

Only images that pass land in object storage **and** the vector store.

### Dedup — three tiers, applied to BOTH modalities, BEFORE insert

| Tier | Text | Images |
|------|------|--------|
| **Exact** | `content_hash` (sha256 of normalized text) | `sha256` of image bytes |
| **Near-dup** | MinHash / SimHash (shingles) | **pHash / dHash** Hamming distance |
| **Semantic** | embedding cosine ≥ threshold | embedding cosine ≥ threshold (Titan multimodal) |

**Enforcement point:** a single **`rag/dedup` gate sits in front of `rag/index`** —
nothing is upserted to the vector store or Postgres until it passes exact → near →
semantic for its modality. The DB is clean *by construction*, not by later cleanup.

```
chunk/image ─▶ quality gate ─▶ EXACT ─▶ NEAR-DUP ─▶ SEMANTIC ─▶ index (DB)
                  (drop junk)    (drop identical)  (drop paraphrase/resave)
```

### Structure additions (extends §0C)

```
engine/
  extract/   # now also pulls <img> + alt + caption + surrounding text
  media/     # NEW: download images, sha256-name, pHash, quality gate
knowledge/
  <site>/<slug>.md
  <site>/images/<sha256>.<ext>      # NEW: stored images
  <site>/images/<sha256>.json       # NEW: sidecar image records
rag/
  embed/     # Titan Multimodal (text + image)
  dedup/     # NEW: exact + near + semantic gate, both modalities
  index/     # upsert ONLY post-dedup
```

### Contract update (extends §0C)

- **Embed → Dedup → Index** (dedup is now a mandatory stage between them).
- A stored record (text or image) is **guaranteed**: passed quality gate **and**
  is unique under exact + near-dup + semantic checks.
- Images carry `page_url` + `surrounding_text` so retrieval stays **grounded and
  citable**, exactly like text chunks.

**PII note:** lighter concern than fine-tuning (a RAG bot retrieves, it doesn't
memorize/regurgitate training data) — but if the sites contain personal data and the
bot will surface it, still scrub.

**Re-crawl / freshness:** since the sites are known and few, add a simple scheduled
re-crawl with `content_hash` change-detection so the knowledge base stays current.
That matters more for you than scaling out.

**Minimal stack to start:** Python + httpx + Trafilatura + a chunker + BGE-M3 +
**one** vector store (Qdrant single-node, **or even** pgvector on Postgres so it's a
single database) + Postgres for metadata. No Celery/Mongo/cluster until a site count
or volume actually forces it.

---

## 1. What changed from v1 and why

| # | v1 design | Problem | v2 fix |
|---|-----------|---------|--------|
| 1 | Frontier LLM ("GPT-5.5") classifies every chunk | Ruinous cost at crawl scale; model doesn't exist | **Tiered relevance**: heuristics → small local classifier → LLM only at generation |
| 2 | Filter & chunk **before** dedup | Pay to embed/classify content you later discard | **Dedup early**: cheap MinHash right after extraction |
| 3 | No robots.txt / rate limit / PII / ToS layer | #1 legal & reputational risk for a dataset publisher | **Mandatory Compliance & Politeness layer** + PII scrubbing |
| 4 | Mongo + Postgres + Qdrant + Redis + FAISS from day 1 | Massive ops surface for a Phase-1 single-page tool | **Infra grows with roadmap phase** |
| 5 | Trafilatura + Readability + BeautifulSoup | Redundant extractors | Trafilatura primary, BS4 fallback, drop Readability |
| 6 | Playwright for every page | 5–10× slower/costlier than needed | **Static HTTP fast-path**, Playwright only on JS pages |
| 7 | No provenance / dataset versioning | RAG needs citations; datasets are mutable artifacts | **Lineage on every chunk** + DVC dataset versioning |
| 8 | Vague quality metrics across all stages | "Hallucination prob." meaningless for extraction | Metrics scoped to the stage they apply to |

---

## 2. Upgraded pipeline (corrected ordering)

```
                ┌─────────────────────────────────────────────────────────┐
                │  COMPLIANCE & POLITENESS LAYER (cross-cutting, mandatory) │
                │  robots.txt · rate-limit/backoff · UA id · ToS allowlist  │
                └─────────────────────────────────────────────────────────┘
 Frontend (Next.js)
      │  URL(s), format, scope
      ▼
 API Gateway (FastAPI)  ── auth, job creation, budget guardrails
      │
      ▼
 Task Queue (Redis + Celery)  ── DLQ + retry/backoff
      │
      ▼
 Crawl Frontier  ── sitemap parse · URL normalize+dedup · depth/scope · change-detect
      │
      ▼
 Fetch Layer
   ├─ Static fast-path (httpx)         ← default, ~80% of pages
   └─ Dynamic (Playwright/Crawl4AI)    ← only when JS/scroll/session needed
      │
      ▼
 Raw Store (object storage / Mongo)  ── keep raw HTML + headers + fetch metadata
      │
      ▼
 Content Extraction (Trafilatura → BS4 fallback)  ── readable text + metadata
      │
      ▼
 Cheap Junk Removal  ── boilerplate, nav, ads, cookie banners (rules)
      │
      ▼
 ⭐ EARLY DEDUP (MinHash / SimHash)  ── exact + near-dupe, BEFORE any AI spend
      │
      ▼
 Tiered Relevance Gate
   ├─ T0 heuristics (length, link-density, language)   ← free
   ├─ T1 small local classifier (MiniLM/BGE head)      ← cheap
   └─ T2 LLM (only on uncertain band)                  ← rare
      │
      ▼
 Semantic Chunking  ── heading-aware + embedding-aware boundaries
      │
      ▼
 Embeddings (BGE-M3)  ── cached by content hash
      │
      ▼
 Semantic Dedup (FAISS / Qdrant cosine)  ── catch paraphrased duplicates
      │
      ▼
 PII Scrubbing (Presidio)  ── before anything leaves the system
      │
      ▼
 Dataset Generation (LLM)  ── QA · instruction · ChatML · RAG chunks
      │                        (the ONLY routine frontier-LLM spend)
      ▼
 Quality Validation + Human-in-the-loop sample review
      │
      ▼
 Export & Vector Store (Qdrant) + DVC-versioned dataset artifacts
```

**Key reorder:** dedup and the cheap relevance gate now run *before* embeddings and
LLM calls, so you only spend compute on content that survives.

---

## 3. Tiered AI strategy (the core cost fix)

The original "LLM judges everything" approach does not survive contact with a real
crawl. Replace it with a **confidence-banded cascade** — each tier only escalates
what it can't decide:

| Tier | Tool | Runs on | Job |
|------|------|---------|-----|
| **T0** | Pure rules | 100% of chunks | Drop obvious junk (too short, high link density, wrong language, nav/footer) |
| **T1** | Small classifier (local, fine-tuned BGE/MiniLM head) | Whatever survives T0 | Score relevance; auto-keep high, auto-drop low |
| **T2** | Frontier LLM (Haiku-class default, Opus for hard cases) | Only the **uncertain middle band** (typ. <10%) | Final relevance judgement |
| **Gen** | Frontier LLM | Kept chunks only | Actually *generate* QA/instruction/ChatML data |

Frontier-model tokens become a small, bounded fraction of the bill instead of the
dominant cost.

---

## 4. Data model & provenance (new, non-negotiable)

Every chunk carries lineage so RAG can cite and audits can trace:

```jsonc
{
  "chunk_id": "uuid",
  "source_url": "https://...",
  "fetched_at": "2026-06-04T...Z",
  "http_status": 200,
  "content_hash": "sha256:...",      // dedup + embedding cache key
  "extractor": "trafilatura",
  "relevance": { "tier": "T1", "score": 0.87 },
  "pii_scrubbed": true,
  "license_note": "robots-allowed; ToS allowlisted",
  "text": "..."
}
```

- **Provenance** = `source_url` + `fetched_at` on everything (required for citations).
- **Dataset versioning** via **DVC** (or LakeFS) — datasets are artifacts that change.
- **Compute caching**: `content_hash` keys both the embedding cache and the LLM cache.

---

## 5. Storage — right-sized per phase

| Store | Purpose | Introduced in |
|-------|---------|---------------|
| SQLite / local files | Phase-1 metadata + JSONL output | Phase 1 |
| PostgreSQL | Structured job/chunk metadata, lineage | Phase 1–2 |
| Object storage (S3/MinIO) or MongoDB | Raw HTML + fetch artifacts | Phase 3 |
| Qdrant | Production vector store | Phase 3 |
| FAISS (in-process) | Fast in-job semantic dedup | Phase 2–3 |
| Redis | Celery broker + rate-limit counters + caches | Phase 2–3 |

Don't stand up the whole zoo for a single-page scraper.

---

## 6. Compliance & Politeness layer (new, mandatory)

Cross-cuts the whole crawl. A dataset publisher cannot skip this.

- **robots.txt** parsing + obey (with per-domain caching).
- **Per-domain rate limiting** + exponential backoff + jitter.
- **Honest `User-Agent`** with contact URL.
- **ToS / domain allowlist** — explicit opt-in for what may be crawled & redistributed.
- **PII detection & scrubbing** (Microsoft Presidio) before export.
- **Copyright/license tagging** carried into the dataset metadata.
- **Kill-switch + per-job budget cap** (max pages, max tokens, max $).

---

## 7. Reliability & observability

- **Celery DLQ** + bounded retries with backoff for fetch/extract/generate failures.
- **Idempotency** via `content_hash` so re-runs don't duplicate work or data.
- **Prometheus + Grafana**: pages/sec, dedup ratio, tier-escalation %, $/1k chunks, queue depth, DLQ size.
- **Cost dashboard** — token spend per job, alarmed against the budget cap.

---

## 8. Revised roadmap (infra follows features)

**Phase 1 — Prove the core (local, no cluster)**
Static fetch → Trafilatura → junk removal → MinHash dedup → JSONL export.
Infra: Python + SQLite/files. *No* Celery/Mongo/Qdrant yet.

**Phase 2 — Add intelligence**
Tiered relevance (T0/T1) · BGE-M3 embeddings + cache · semantic chunking ·
QA generation (LLM) · quality validation · PII scrubbing.
Infra: Postgres, Redis+Celery, FAISS.

**Phase 3 — Scale out**
Playwright dynamic path · crawl frontier + sitemaps · multi-page crawl ·
semantic dedup at scale · Qdrant · raw object storage · provenance + DVC.
Infra: full distributed stack, Docker.

**Phase 4 — Enterprise**
Autonomous crawl agents · incremental re-crawl/change-detection ·
human-in-the-loop review console · enterprise RAG connectors · multi-tenant + SSO.
Infra: K8s/autoscaling, full observability.

---

## 9. Final positioning (unchanged intent, hardened)

CortexCrawler AI remains a **semantic knowledge-extraction and AI dataset-generation
platform**, not a scraper. v2 makes it *shippable*: cheap-before-expensive ordering,
a tiered AI cascade instead of brute-force LLM, a mandatory legal/PII layer,
provenance on every record, and infrastructure that grows with the roadmap instead
of all at once.
