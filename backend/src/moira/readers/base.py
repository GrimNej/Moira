"""Link readers (§7.3.2): results are frozen into ``research`` rows at save time."""

from dataclasses import dataclass, field

from moira.capture.urls import canonicalize, platform
from moira.readers.ssrf import SafeFetcher

BLOCKED_STATUS = (401, 403, 429, 451)


@dataclass
class ReaderResult:
    method: str  # youtube_oembed | github_api | page_fetch | web_search
    status: str  # ok | blocked | error | not_found | skipped
    title: str = ""
    author: str = ""
    findings: str = ""
    excerpt: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)


async def read_link(url: str, fetcher: SafeFetcher | None = None) -> ReaderResult:
    """Pick the reader by platform. Walled platforms make no request."""
    from moira.readers import github, page, walled, youtube

    canonical = canonicalize(url)
    name = platform(canonical.split("/")[2] if "//" in canonical else canonical)
    if name == "youtube":
        return await youtube.read(canonical)
    if name == "github":
        return await github.read(canonical)
    if name in walled.WALLED:
        return await walled.read(canonical)
    return await page.read(canonical, fetcher or SafeFetcher())
