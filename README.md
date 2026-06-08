# CortexCrawler AI

Crawl websites into clean, deduplicated **markdown + images** for RAG / chatbot
knowledge bases. CortexCrawler does one job well: turn a site into a tidy
`knowledge/<site>/` folder of `.md` files (with provenance front-matter) plus
quality-filtered, deduplicated images. **Chunking, embedding, and retrieval are
out of scope by design** — your existing RAG pipeline consumes the output.

Installable Python package (`cortexcrawler`), zero config required.

## Install

```bash
pip install "git+https://github.com/Jignesh160/Context-Crawler-AI.git"
pip install "cortexcrawler[dynamic]"   # optional: Playwright for JS / SPA sites
```

## Use from your pipeline (the public API)

```python
from cortexcrawler import KnowledgeBase

kb = KnowledgeBase()                      # built-in defaults; or KnowledgeBase(config=load_config("my.yaml"))
paths = kb.crawl("https://your-site.com/")  # -> knowledge/<site>/*.md (+ images/)
# then point YOUR chunker/embedder/retriever at the knowledge/ folder
```

That's the whole surface. See [examples/use_crawler.py](examples/use_crawler.py).

## CLI

```bash
cortex-crawl "https://your-site.com/" --max-pages 20 --max-depth 2
```

## Output

```
knowledge/<site>/<slug>.md              # clean markdown + image refs + YAML front-matter
knowledge/<site>/images/<sha256>.jpg    # kept images, content-addressed
knowledge/<site>/images/<sha256>.json   # per-image provenance sidecar (alt, caption, page_url, ...)
```

Each `.md` front-matter carries `source_url`, `title`, `fetched_at`, `content_hash`
and the page's image refs — everything your RAG ingest needs for citations.

## Works on any site type

Auto-adapts to how a page delivers content — no per-site config:

| Site type | How it's handled |
|-----------|------------------|
| Static HTML / WordPress / server-rendered | Fast static fetch (httpx) |
| Nuxt / Next **SSR** | Static fetch + section-heading re-injection |
| **SPA / client-rendered** (React/Vue/Angular/Svelte) | Auto-detected shell → headless Chromium render |

Static-first for speed; a real browser is used only when a page is thin or is an
unhydrated SPA shell. For the browser path: `pip install "cortexcrawler[dynamic]"`
then `playwright install chromium`.

### Crawling all pages on JS-navigation sites

Some sites build their **navigation menu with JavaScript**, so the links to other
pages don't exist in the static HTML — a normal crawl then only reaches the handful
of links that *are* static. Use `--render-mode always` (or `crawl.render_mode:
always`) to render every page in a browser and discover the JS-rendered nav links,
so the crawl reaches the whole site:

```bash
cortex-crawl "https://your-site.com/" --render-mode always --max-pages 50 --max-depth 3
```

This is slower (every page goes through the browser) but complete. Default `auto`
renders only when a page is thin/SPA. Tip: you can also just pass known page URLs as
separate seeds.

## Extraction quality

- **Section headings preserved.** Even when the extractor would flatten a page
  (e.g. Nuxt SSR), CortexCrawler re-injects the real `##`/`###` headings so your
  chunker can split by topic.
- **Meaningful content only** — boilerplate/nav removed; repeated site-title/nav
  chrome stripped across pages; split number/label "stat cards" re-paired
  (`Combined Power: 449 Hp (335 kW)`).
- **No junk images** — quality gate drops icons/spacers/banners/logos by
  size / aspect / byte-size / type.
- **No duplicates** — text: sha256 + MinHash across pages; images: sha256 +
  **perceptual hash** (catches resized/re-saved copies).
- **Polite** — per-domain rate limiting, honest User-Agent. `obey_robots` is
  `false` by default (first-party crawling); set it `true` for third-party sites.

## Crawl scope

Limit what gets crawled in `config/settings.yaml` (excluded URLs are never fetched
or emitted):

```yaml
crawl:
  include: []                       # if set, only matching URL globs are crawled
  exclude: ["*/cookies*", "*/privacy*", "*/request-for-quote*", "*/login*"]
```

## Configuration

Built-in defaults work out of the box. Override via a `config/settings.yaml` in the
working dir (or `$CORTEX_CONFIG`). All knobs — rate limit, depth, image gates, dedup
thresholds, dynamic-render fallback, scope globs — live there.

## Project layout

```
src/cortexcrawler/
  engine/    crawler: fetch, politeness, extract, media, dedup, emit, crawl, dynamic
  api.py     KnowledgeBase — the public API your pipeline imports
  cli.py     console entry point: cortex-crawl
  log.py     logging
knowledge/   OUTPUT — markdown + images (what your RAG pipeline ingests)
config/      optional settings.yaml (defaults are built in)
tests/       pytest suite
```

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check src tests
```
