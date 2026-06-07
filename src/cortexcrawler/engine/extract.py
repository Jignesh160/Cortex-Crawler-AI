"""Content extraction (ARCHITECTURE_FINAL.md §3).

HTML -> clean markdown via trafilatura (the reusable primitive), plus our own image
discovery pass that pulls <img> tags from the main content with alt/caption/context.
We own the orchestration; we stand on trafilatura + BeautifulSoup for the plumbing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup


@dataclass
class DiscoveredImage:
    src_url: str
    alt: str = ""
    caption: str = ""
    surrounding_text: str = ""


@dataclass
class Extraction:
    title: str
    lang: str
    markdown: str
    text_len: int
    images: list[DiscoveredImage] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # for the crawl frontier


_WS = re.compile(r"\s+")
# Common client-rendered-app mount points: if present with little server-rendered
# text, the real content is built by JavaScript and needs a browser to extract.
_SPA_ROOT_IDS = {"app", "__nuxt", "__next", "root", "q-app", "___gatsby", "svelte"}
_HEAD_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = {"p", "li", "td", "th", "blockquote", "figcaption", "dd", "dt"}
_SIG_LEN = 60          # chars of normalized text used as a block signature
_MIN_SIG = 12          # ignore blocks shorter than this (noise)


def _clean(text: str | None) -> str:
    return _WS.sub(" ", (text or "")).strip()


def _norm(text: str | None) -> str:
    """Normalize to lowercase alnum words for robust block matching."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _existing_headings(md: str) -> set[str]:
    return {_norm(m.group(1)) for m in re.finditer(r"(?m)^#{1,6}\s+(.*)$", md)}


def _is_stat_value(s: str) -> bool:
    """A short 'stat card' value like '449 Hp (335 kW)', '505 N·m', '995km'."""
    s = s.strip()
    if not (2 <= len(s) <= 40):
        return False
    if not re.match(r"^[~<>≈]?\s*\d", s):       # starts with a number
        return False
    if not re.search(r"[A-Za-z°%·/]", s):        # carries a unit
        return False
    if s.endswith((".", "!", "?")):              # not a sentence
        return False
    return len(s.split()) <= 5


def _is_stat_label(s: str) -> bool:
    """A short descriptive label like 'Combined Power', 'Maximum Torque'."""
    s = s.strip()
    if not (2 <= len(s) <= 40):
        return False
    if any(ch.isdigit() for ch in s):
        return False
    if s[:1] in {"#", "-", "*", "|", "!", "[", ">"}:
        return False
    if s.endswith((".", "!", "?", ":")):
        return False
    return 1 <= len(s.split()) <= 5


def _pair_stat_cards(md: str) -> str:
    """Join adjacent value/label 'stat card' blocks into 'Label: Value' so a
    number and its meaning stay together (helps both reading and retrieval)."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", md)]
    out: list[str] = []
    i = 0
    while i < len(blocks):
        a = blocks[i]
        b = blocks[i + 1] if i + 1 < len(blocks) else None
        if b is not None and _is_stat_value(a) and _is_stat_label(b):
            out.append(f"{b}: {a}")
            i += 2
        elif b is not None and _is_stat_label(a) and _is_stat_value(b):
            out.append(f"{a}: {b}")
            i += 2
        else:
            out.append(blocks[i])
            i += 1
    return "\n\n".join(out)


def _inject_headings(html: str, base_md: str) -> str:
    """Restore section headings that Trafilatura dropped.

    Trafilatura removes boilerplate well but, for some DOMs (e.g. Nuxt SSR), it
    discards <h2>/<h3> entirely, flattening pages. We re-insert each real heading
    immediately before the first kept content block it introduces, in document
    order. Headings that only precede dropped boilerplate are naturally skipped.
    """
    if not base_md.strip():
        return base_md

    soup = BeautifulSoup(html, "lxml")
    for junk in soup(["script", "style", "noscript", "template"]):
        junk.decompose()

    # Signatures of content blocks Trafilatura kept.
    kept_sigs = [_norm(ln)[:_SIG_LEN] for ln in base_md.splitlines() if _norm(ln)]
    kept_set = {s for s in kept_sigs if len(s) >= _MIN_SIG}

    def is_kept(text: str) -> bool:
        s = _norm(text)[:_SIG_LEN]
        if len(s) < _MIN_SIG:
            return False
        if s in kept_set:
            return True
        head = s[:30]
        return any(k.startswith(head) or s.startswith(k[:30]) for k in kept_set)

    # Walk the DOM in order: sequence of headings and content blocks.
    body = soup.body or soup
    seq: list[tuple] = []
    for el in body.find_all(list(_HEAD_TAGS | _BLOCK_TAGS)):
        if el.name in _HEAD_TAGS:
            txt = _clean(el.get_text())
            if txt:
                seq.append(("h", int(el.name[1]), txt))
        else:
            seq.append(("c", el.get_text()))

    # Map each real heading -> signature of the first kept block it introduces.
    already = _existing_headings(base_md)
    targets: dict[str, list[tuple[int, str]]] = {}
    for i, item in enumerate(seq):
        if item[0] != "h":
            continue
        lvl, htext = item[1], item[2]
        if _norm(htext) in already:  # don't duplicate headings trafilatura kept
            continue
        target = None
        for j in range(i + 1, len(seq)):
            if seq[j][0] == "h":
                break
            if is_kept(seq[j][1]):
                target = _norm(seq[j][1])[:_SIG_LEN]
                break
        if target:
            targets.setdefault(target, []).append((lvl, htext))

    if not targets:
        return base_md

    # Rebuild markdown, inserting heading groups before their target line.
    out: list[str] = []
    done: set[str] = set()
    for ln in base_md.splitlines():
        sig = _norm(ln)[:_SIG_LEN]
        if sig in targets and sig not in done:
            for lvl, htext in targets[sig]:
                out.append("#" * min(lvl, 6) + " " + htext)
            out.append("")
            done.add(sig)
        out.append(ln)
    return "\n".join(out)


def is_spa_shell(html: str, text_threshold: int = 1500) -> bool:
    """True if the HTML looks like an unhydrated client-rendered app shell.

    Heuristic: a known SPA mount node is present but the server-delivered body
    text is small. Server-rendered/static pages (rich body text) return False, so
    this only forces a browser render for genuinely JS-built pages.
    """
    soup = BeautifulSoup(html, "lxml")
    body = soup.body
    if body is None:
        return False
    if len(_clean(body.get_text())) >= text_threshold:
        return False  # plenty of server-rendered content; no browser needed
    for el in soup.find_all(id=True):
        if el.get("id") in _SPA_ROOT_IDS:
            return True
    return False


def _discover_images(html: str, base_url: str) -> list[DiscoveredImage]:
    soup = BeautifulSoup(html, "lxml")
    out: list[DiscoveredImage] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        abs_src = urljoin(base_url, src)
        if abs_src in seen:
            continue
        seen.add(abs_src)

        alt = _clean(img.get("alt"))
        # caption: a nearby <figcaption>, else the parent's text as context
        caption = ""
        fig = img.find_parent("figure")
        if fig and fig.find("figcaption"):
            caption = _clean(fig.find("figcaption").get_text())
        parent = img.find_parent(["figure", "p", "div", "section"])
        surrounding = _clean(parent.get_text()) if parent else ""
        surrounding = surrounding[:500]

        out.append(DiscoveredImage(abs_src, alt, caption, surrounding))
    return out


def _discover_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("#")[0]
        if href.startswith(("http://", "https://")) and href not in seen:
            seen.add(href)
            links.append(href)
    return links


def extract(html: str, url: str) -> Extraction:
    # Primary text extraction -> markdown (headings/lists/tables preserved).
    md = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_links=True,
        favor_recall=True,
        url=url,
    ) or ""

    # Restore section headings that Trafilatura's extraction dropped, then
    # re-pair split number/label "stat cards".
    md = _inject_headings(html, md)
    md = _pair_stat_cards(md)

    meta = trafilatura.extract_metadata(html)
    title = (meta.title if meta and meta.title else "") or "Untitled"
    lang = (meta.language if meta and getattr(meta, "language", None) else "") or ""

    return Extraction(
        title=_clean(title),
        lang=lang,
        markdown=md.strip(),
        text_len=len(md),
        images=_discover_images(html, url),
        links=_discover_links(html, url),
    )
