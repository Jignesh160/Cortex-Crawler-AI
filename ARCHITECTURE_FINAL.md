# CortexCrawler AI — Final Architecture

> **⚠️ Scope note (current):** The shipped tool is a **crawler only** — it produces
> clean `.md` + images for an external RAG pipeline to consume. The RAG layer
> described below (chunking, embeddings, S3 Vectors, Nova) was built and validated
> but later **removed** because the consuming chatbot owns chunking/embedding/
> retrieval. This document is retained as design history; for current behavior see
> `README.md` and `CHANGELOG.md`.

> **Definitive design.** Consolidates every decision made during planning.
> Supersedes the original PDF and `ARCHITECTURE_v2.md`.

---

## 1. What this is (locked scope)

A **multimodal RAG knowledge base builder**: crawl a small set of **known, permitted
sites**, extract **text + images**, clean them into **markdown** (the source of truth),
and serve a chatbot that **retrieves grounded, cited content** at query time.

**Decisions that shape everything below:**

| Decision | Choice |
|----------|--------|
| Primary use | **RAG knowledge base** (retrieve real content — *not* fine-tuning / not generating conversations) |
| Sources | **A few known sites** (no open-web, no distributed crawl) |
| Modalities | **Text + images** |
| Consumption | The **chatbot ingests the `.md` file directly** (text + image URLs); vectors only *select* which files |
| Canonical store | **Markdown files** (`.md`) + S3-hosted images; vectors are a rebuildable index |
| Image delivery | **Hosted in S3, referenced by URL** in the markdown (Nova fetches them) |
| Crawl engine | **Built in-house**, Crawl4AI-style (own the orchestration, reuse primitives) |
| Cloud / models | **AWS Bedrock** — Titan Multimodal Embeddings + Amazon Nova |
| Vector store | **Amazon S3 Vectors** (native, low-cost; store + vectors both live in S3) |
| DB guarantee | **No duplicates, no junk — enforced before insert, both modalities** |

---

## 2. The one architectural idea that makes it all work

```
   engine/  ──writes .md + images──▶  knowledge/  ──reads files──▶  rag/
  (crawler)                          (source of truth)          (AWS RAG layer)
```

Three independent zones joined by **stable contracts**. The **file is the seam**: the
crawler's only job is to produce well-formed markdown + images + provenance.
Everything downstream reads files, never crawler internals. Consequences:

- **Engine is hot-swappable** — your crawler ↔ Crawl4AI, same `.md` contract.
- **Models are config, not code** — swap Titan/Nova without touching logic.
- **Index is rebuildable** — vectors derive from files; re-embed anytime.
- **Database is clean by construction** — a dedup+quality gate guards every insert.

---

## 3. End-to-end pipeline

```
 ┌── COMPLIANCE (cross-cutting): robots.txt · rate-limit+backoff · honest UA · ToS allowlist ──┐
 │                                                                                              │
 │   known URLs / sitemaps                                                                      │
 │        ▼                                                                                     │
 │   FETCH dispatcher ── static (httpx) by default → Playwright only if JS-heavy                │
 │        ▼                                                                                      │
 │   EXTRACT ── HTML → clean markdown ("fit markdown") + pull <img> (alt, caption, context)     │
 │        ▼                                                                                      │
 │   MEDIA ── download images, sha256-name, pHash, IMAGE QUALITY GATE (drop chrome)             │
 │        ▼                                                                                      │
 │   JUNK FILTER ── pruning + BM25 (text) ── drop low-value nodes                               │
 │        ▼                                                                                      │
 │   EARLY DEDUP ── MinHash across pages (text) · sha256+pHash (images)                         │
 │        ▼                                                                                      │
 │   EMIT ──▶ knowledge/<site>/<slug>.md  +  images/<sha256>.<ext> (+ .json sidecar)            │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
          │  (the seam — files only)
          ▼
   CHUNK ── heading-aware + semantic boundaries (split on markdown headings)
          ▼
   EMBED ── Amazon Titan Multimodal Embeddings (text + images, one vector space)
          ▼
   DEDUP+QUALITY GATE ── exact → near-dup → semantic, BOTH modalities   ← guards the DB
          ▼
   PII SCRUB ── Presidio (only if sites contain personal data)
          ▼
   INDEX ── upsert to Amazon S3 Vectors (text + image vectors + metadata)
          ▼
   RETRIEVE ── S3 Vectors similarity (+ optional keyword) ──▶ select .md / chunks
          ▼
   ANSWER ── Amazon Nova Lite (multimodal): reads markdown + fetches image URLs, cited
```

**Why this order:** all *cheap* filtering and dedup happen **before** any paid AI
spend, and the markdown is written **before** chunk/embed so the files (not the
vectors) are the durable artifact.

---

## 4. Models (AWS Bedrock) — best fit per job

| Job | Model | ID | Why |
|-----|-------|-----|-----|
| **Embeddings** (text + image) | **Titan Multimodal Embeddings** | `amazon.titan-embed-image-v1` | One shared vector space → text query retrieves images & vice versa |
| **Answer synthesis** (default) | **Amazon Nova Lite** | `amazon.nova-lite-v1:0` | Fast, cheap, multimodal — ideal for "answer from retrieved chunks" |
| Answer (harder reasoning) | Amazon Nova Pro | `amazon.nova-pro-v1:0` | Step up only if answer quality demands |
| Answer (cheapest, text-only) | Amazon Nova Micro | `amazon.nova-micro-v1:0` | Minimum cost |

> **Optional dual-embedder:** if *pure-text* retrieval quality is critical, run Titan
> **Text V2** (`amazon.titan-embed-text-v2:0`) for text chunks + Multimodal for images,
> in two collections. Default = single multimodal space for simplicity. This is a
> `config/` switch, never a code change.

**No frontier-LLM crawl cost.** Unlike the original "GPT-5.5 classifies every chunk,"
the only routine model calls are embeddings (cheap) and runtime answers. There is
**no dataset-generation LLM** — RAG retrieves originals.

---

## 5. The clean-database guarantee (your hard requirement)

**Nothing enters the DB until it passes a quality gate AND is unique.** Enforced by a
single `rag/dedup` stage in front of `rag/index`, for **both** modalities.

### Quality gates (kill "unmeaningful")

**Text:** pruning (low text-density nodes), BM25 relevance, min-length, language.
**Images** (cheap → escalate):

| Tier | Check | Drops |
|------|-------|-------|
| R0 size | < ~100px or tiny area | icons, spacers, tracking pixels |
| R0 aspect | extreme ratio (>10:1) | banners, dividers |
| R0 role | logo/avatar/sprite/SVG-icon by filename/CSS/role | UI chrome |
| R1 info | tiny byte-size / low color entropy | blanks, solid fills |
| R2 (optional) | vision "is this content?" check | decorative stock imagery |

### Dedup — 3 tiers, both modalities, before insert

| Tier | Text | Images |
|------|------|--------|
| **Exact** | sha256 of normalized text | sha256 of bytes |
| **Near-dup** | MinHash / SimHash | **pHash / dHash** Hamming distance |
| **Semantic** | embedding cosine ≥ θ | embedding cosine ≥ θ (Titan multimodal) |

```
candidate ─▶ QUALITY GATE ─▶ EXACT ─▶ NEAR-DUP ─▶ SEMANTIC ─▶ INDEX
              (drop junk)    (identical) (resized/  (paraphrase/
                                          shingled)  re-rendered)
```

> **Why pHash matters:** the same image resized/re-saved has different bytes, so
> sha256 alone leaks duplicates. Perceptual hashing catches the visual near-copies.

---

## 6. Data contracts (the stable boundaries)

### 6.1 Crawler → Knowledge (the critical seam)

One `.md` per page; the engine's *only* downstream-visible output.

```yaml
---
source_url: string        # required — citation + re-crawl key
title: string             # required
fetched_at: iso8601       # required — freshness
content_hash: sha256      # required — dedup + change-detect + embed cache key
section_path: string      # optional — "Docs > Getting Started > Intro"
lang: string              # optional (default en)
status: ok | partial | empty
---
# clean markdown body, with ![alt](https://cdn.../<sha256>.png) S3/CloudFront URLs
```

> The chatbot ingests this `.md` directly: it reads the text and **fetches each image
> by its S3/CloudFront URL** (Nova is multimodal). The `.md` stays small and portable;
> the heavy bytes stay in S3.

### 6.2 Image record (sidecar JSON, per kept image)

```yaml
image_id: sha256
s3_url: string            # hosted location the markdown references (S3/CloudFront)
page_url: string          # provenance — where found
src_url: string           # original image URL
alt: string
caption: string
surrounding_text: string  # context for retrieval + grounding
width: int
height: int
phash: string             # near-dup detection
status: kept | dropped
drop_reason: null | chrome | too_small | duplicate | low_info
```

### 6.3 Downstream contracts

- **Knowledge → RAG:** `rag/` reads `knowledge/**/*` only; never imports `engine/`.
- **Chunk:** `Chunk{ id, source_url, section_path, text, content_hash }`.
- **Embed → Dedup → Index:** model ID from `config/`; nothing upserts pre-dedup.
- **Retrieve → Answer:** retrieval returns ranked items **with `source_url`** so Nova
  cites; images returned with `page_url` + `surrounding_text` for grounding.
- **Guarantee:** any stored record passed quality + is unique under exact/near/semantic.

---

## 7. Project structure

```
contextcrawler/
├── engine/                       # in-house Crawl4AI-style crawler
│   ├── fetch/                    #   static (httpx) + dynamic (Playwright) dispatcher
│   ├── politeness/               #   robots, rate-limit, backoff, proxy, UA
│   ├── extract/                  #   HTML → markdown + pull <img>+alt+caption+context
│   ├── media/                    #   download images, sha256, pHash, quality gate
│   ├── filter/                   #   pruning + BM25 (core IP)
│   ├── crawl/                    #   deep-crawl frontier (BFS/DFS), URL dedup, scope
│   ├── state/                    #   resumable checkpoints
│   └── emit/                     #   writes .md + images + sidecar  ← THE SEAM
│
├── knowledge/                    # SOURCE OF TRUTH (rebuildable index derives from this)
│   └── <site>/
│       ├── <slug>.md
│       └── images/<sha256>.<ext> + <sha256>.json
│
├── rag/                          # AWS layer — reads knowledge/ only
│   ├── chunk/                    #   heading-aware + semantic chunking
│   ├── embed/                    #   Titan Multimodal Embeddings
│   ├── dedup/                    #   exact + near + semantic gate (both modalities)
│   ├── index/                    #   upsert ONLY post-dedup
│   ├── retrieve/                 #   hybrid (BM25 + vector)
│   └── answer/                   #   Nova Lite, multimodal, cited
│
├── pipeline/                     # orchestration: crawl → index → serve
├── config/                       # site list, scope, thresholds, MODEL IDs
└── tests/
```

**Own the orchestration, reuse the primitives.** Build the smart parts (fetch routing,
filtering, deep-crawl scheduling, provenance); stand on Playwright + lxml/selectolax +
markdownify + rank-bm25 + imagehash for the plumbing. Do not write a browser or a
markdown serializer from scratch.

---

## 8. Storage — S3-centric

Everything of value lives in S3: the markdown, the images, and the vectors. One
storage backbone, AWS-native, minimal ops.

| Store | Purpose | Notes |
|-------|---------|-------|
| **S3 — knowledge bucket** | `knowledge/` markdown (`.md`) | **Source of truth**; the chatbot reads these |
| **S3 — image bucket** (+ CloudFront) | images, content-addressed `<sha256>.<ext>` | Referenced by URL from the markdown; Nova fetches them |
| **Amazon S3 Vectors** ⭐ | text + image embeddings + metadata, similarity search | Native, low-cost vector store; **replaces pgvector/Qdrant** |
| Lightweight metadata (DynamoDB or S3 manifest) | crawl state, lineage, `content_hash` ledger | For dedup ledger + freshness; keep it simple |
| Redis | rate-limit counters, caches | Add only when crawl volume needs it |

**Why S3 Vectors:** store *and* vectors share one backbone, costs a fraction of a
hosted vector DB at this scale, and integrates with Bedrock. Image and text vectors
(both from Titan Multimodal) sit in the same index → cross-modal retrieval out of the
box. Move to OpenSearch/Qdrant only if you outgrow S3 Vectors' query needs.

---

## 9. Cross-cutting requirements

- **Compliance:** robots.txt, per-domain rate-limit + backoff, honest UA, ToS allowlist.
- **Provenance:** `source_url` + `fetched_at` on every text chunk *and* image — non-
  negotiable for citations and audits.
- **Freshness:** scheduled re-crawl of the known sites with `content_hash` change
  detection — only re-embed what changed. (Matters more than scaling out, for you.)
- **PII:** Presidio scrub before insert if sites contain personal data (lighter concern
  for RAG than fine-tuning, but a retrieved chunk can still surface PII).
- **Caching:** `content_hash` keys both the embedding cache and any LLM cache.
- **Observability:** Prometheus + Grafana — pages/sec, dedup ratio, % images kept,
  $/answer, queue depth. Cost dashboard alarmed against a per-job budget cap.

---

## 10. Build roadmap (infra follows features)

**Phase 1 — Prove the core (local, no cluster).**
Static fetch → markdown + front-matter (one page) → politeness → pruning filter →
write `.md`. Add image extract + sha256/pHash + quality gate.
*Stack: Python + httpx + lxml + markdownify + imagehash + SQLite/files.*

**Phase 2 — Make it a knowledge base.**
Deep crawl (BFS + frontier + scope + resume) across your few sites → push markdown to
S3 + images to S3/CloudFront → chunking → Titan Multimodal embeddings → dedup gate
(3-tier, both modalities) → **Amazon S3 Vectors** → retrieval selects `.md` files →
Nova Lite reads them (text + image URLs), cited.
*Add: Bedrock, S3 (knowledge + images), S3 Vectors, CloudFront.*

**Phase 3 — Harden & keep fresh.**
Scheduled re-crawl + change detection, PII scrub, observability + cost caps,
Playwright path for JS-heavy sites, optional dual-embedder.
*Add: Redis if volume needs it; OpenSearch/Qdrant only if you outgrow S3 Vectors.*

**Phase 4 — Optional scale.**
Distributed crawl (Celery), multi-tenant, more sites, autonomous re-crawl agents —
**only if** the site count actually grows beyond "a few."

---

## 11. Positioning

CortexCrawler AI is a **multimodal semantic knowledge-extraction platform for RAG**:
it turns a curated set of sites into a clean, deduplicated, cited, text-and-image
knowledge base that a chatbot retrieves from. The design's strengths are **cheap-
before-expensive ordering**, **markdown-as-source-of-truth with a swappable engine**,
**a database that is clean by construction**, and **AWS-native multimodal models** —
all sized to grow only as far as the workload actually requires.
