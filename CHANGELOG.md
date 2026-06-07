# Changelog

## Unreleased — scope narrowed to a pure crawler

**Breaking:** removed the entire `rag/` layer (chunking, chunks.jsonl export,
file-watch, embeddings, vector store, retrieval, answer) and the Bedrock/S3 Vectors
integration. CortexCrawler now does exactly one thing: **crawl → clean `.md` +
images**. Chunking/embedding/retrieval belong to the consuming RAG pipeline.

- Removed CLIs `cortex-index`, `cortex-ask`, `cortex-chunks`, `cortex-watch` and the
  `cortex-crawl --chunks` flag. Remaining CLI: **`cortex-crawl`**.
- Public API trimmed to `KnowledgeBase().crawl(url)`; dropped `index/search/ask/
  crawl_and_chunk/for_aws`.
- Removed the `[aws]` extra and `numpy` dependency. Config no longer has a `rag`
  section or AWS env overrides.
- All extraction quality (heading preservation, image/text dedup, stat-card
  pairing, boilerplate stripping, scope globs, any-render-type support) is retained.

## Earlier — extraction & chunking quality for RAG

Focus: produce **section-structured, single-topic** chunks instead of flattened
paragraphs. Evaluated against a real Nuxt SSR site (icaurbahrain.com).

### Highlighted fix — section headings are preserved (Tier 1)
Trafilatura's extraction was **dropping `<h2>`/`<h3>` headings** for some DOMs
(e.g. Nuxt SSR), flattening pages into undifferentiated paragraphs and crippling
downstream chunking. We now **re-inject section headings**: keep Trafilatura's
clean, boilerplate-free markdown, then walk the original DOM and insert each real
heading before the first kept content block it introduces. Headings that only
precede dropped boilerplate are skipped; headings Trafilatura kept aren't
duplicated.

> Reference page `icaurbahrain.com/iCAURV27REEV`: **0 → 19 headings** (Design,
> Premium Interior, REEV Technology, Safety, Specifications, …). Verified general
> on a second site (docs.python.org: 12/12 headings preserved).

### Heading-aware chunking (Tier 2)
- `rag/chunk` splits on heading boundaries first, then size-caps within a section.
  Each chunk carries its leaf `heading` (folded into the text for embedding
  context) plus `source_url`. Design / Performance / Safety / Interior / Specs
  now become **separate single-topic chunks**.

### Intra-page near-duplicate removal (Tier 2)
- `engine/dedup` adds `shingles`/`jaccard`/`NearDupFilter`. The chunker drops a
  block that repeats an earlier block on the **same page** (e.g. specs shown both
  as flattened text and as a table).

### Cleanup & scope (Tier 3)
- **Stat cards**: split number/label pairs are re-joined
  (`Combined Power: 449 Hp (335 kW)`); prose is left untouched.
- **Global boilerplate**: a site title / nav line repeating across many pages
  (incl. a generic page-title H1) is stripped post-crawl; unique titles survive.
- **Image titles**: fall back `alt → caption → surrounding_text`.
- **Crawl scope**: new `crawl.include` / `crawl.exclude` URL globs. Excluded URLs
  (cookies, legalNotice, privacy, request-for-quote, …) are never fetched or
  emitted.

### RAG-ready chunk export (Tier 4)
- New `cortex-chunks` command + `rag/export.export_chunks()` write
  `datasets/chunks.jsonl`, one record per chunk:
  `{chunk_id, text, heading, section_path, source_url, title, topic, modality,
  image_url, images}` — so consumers don't have to re-chunk the markdown.
- New `cortex-watch` command + `rag/watch.watch_and_export()` keep
  `chunks.jsonl` in sync automatically: any add/edit/remove of a `.md` under
  `knowledge/` triggers a re-export (mtime polling, dependency-free).

### Works on any render type
- `engine/extract.is_spa_shell()` detects unhydrated client-rendered app shells
  (React/Vue/Angular/Svelte mount nodes with little server text). The crawler now
  forces a headless-browser render for SPA shells, in addition to thin/failed
  pages — so static, SSR, and fully client-rendered sites all extract correctly.
  SSR/static pages with real content are never needlessly rendered.

### Compatibility
- No CLI breakage: `cortex-crawl` / `cortex-index` / `cortex-ask` unchanged;
  `cortex-chunks` added. JS/Playwright dynamic-fallback path still works.
- Test suite expanded (extraction headings, chunking, intra-page dedup,
  stat cards, boilerplate, scope, image titles, export).
