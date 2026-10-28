"""Public web pages (§7.3.2): SSRF-guarded GET, HTML only, title + metadata + main text."""

import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from moira.errors import SsrfBlocked
from moira.readers.base import BLOCKED_STATUS, ReaderResult
from moira.readers.ssrf import SafeFetcher

JS_WALL = re.compile(
    r"(?i)enable javascript|javascript is (?:required|disabled)|turn on javascript"
)
STRIP = "script, style, nav, header, footer, aside, form, noscript, svg"


def _meta(tree: HTMLParser, *names: str) -> str:
    for name in names:
        node = tree.css_first(f'meta[property="{name}"]') or tree.css_first(f'meta[name="{name}"]')
        if node is not None and node.attributes.get("content"):
            return str(node.attributes["content"]).strip()
    return ""


def extract(html: str) -> tuple[str, str, str, str]:
    """(title, author, description with the site name, main text)."""
    tree = HTMLParser(html)
    title_node = tree.css_first("title")
    title = _meta(tree, "og:title") or (title_node.text(strip=True) if title_node else "")
    author = _meta(tree, "author", "article:author")
    site = _meta(tree, "og:site_name")
    desc = _meta(tree, "og:description", "description")
    for node in tree.css(STRIP):
        node.decompose()
    main = tree.css_first("article") or tree.css_first("main") or tree.body
    text = re.sub(r"\s+", " ", main.text(separator=" ", strip=True)) if main is not None else ""
    if site:
        desc = f"{desc} ({site})" if desc else site
    return (title or site)[:300], author[:120], desc[:600], text


async def read(canonical: str, fetcher: SafeFetcher) -> ReaderResult:
    try:
        res = await fetcher.get(canonical)
    except SsrfBlocked:
        return ReaderResult("page_fetch", "blocked")
    except Exception:  # noqa: BLE001  # timeouts and network errors: research takes over
        return ReaderResult("page_fetch", "error")
    if res.status in BLOCKED_STATUS:
        return ReaderResult("page_fetch", "blocked")
    if res.status != 200 or not res.text.strip():
        return ReaderResult("page_fetch", "blocked" if res.status in (200, 415) else "error")
    if res.content_type == "text/plain":
        return ReaderResult(
            "page_fetch", "ok", excerpt=res.text[:3000], sources=[{"url": canonical, "title": ""}]
        )
    title, author, desc, text = extract(res.text)
    if (not text or len(text) < 40) and JS_WALL.search(res.text):
        return ReaderResult("page_fetch", "blocked")
    if not title and not text:
        return ReaderResult("page_fetch", "blocked")
    return ReaderResult(
        "page_fetch",
        "ok",
        title=title,
        author=author,
        findings=desc,
        excerpt=text[:3000],
        sources=[{"url": res.final_url, "title": title}],
    )
