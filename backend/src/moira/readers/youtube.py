"""YouTube oEmbed reader: title and channel name (§7.3.2)."""

import httpx

from moira.readers.base import BLOCKED_STATUS, ReaderResult

OEMBED = "https://www.youtube.com/oembed"


async def read(canonical: str) -> ReaderResult:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0)) as client:
            r = await client.get(OEMBED, params={"url": canonical, "format": "json"})
    except httpx.HTTPError:
        return ReaderResult("youtube_oembed", "error")
    if r.status_code in BLOCKED_STATUS or r.status_code == 404:
        return ReaderResult("youtube_oembed", "blocked")
    if r.status_code != 200:
        return ReaderResult("youtube_oembed", "error")
    data = r.json()
    title, author = str(data.get("title", "")), str(data.get("author_name", ""))
    if not title:
        return ReaderResult("youtube_oembed", "blocked")
    return ReaderResult(
        "youtube_oembed",
        "ok",
        title=title,
        author=author,
        findings=f'YouTube video "{title}" by {author}.'.strip(),
        sources=[{"url": canonical, "title": title}],
    )
