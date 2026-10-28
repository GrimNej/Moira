"""Walled platforms (§7.3.2): no request. We never scrape behind logins (ADR 0009)."""

from moira.capture.urls import canonicalize, handle_from_url, platform, post_id
from moira.readers.base import ReaderResult

WALLED = {"instagram", "x", "tiktok", "facebook", "threads", "linkedin"}
LABELS = {
    "instagram": "Instagram post",
    "x": "Post on X",
    "tiktok": "TikTok video",
    "facebook": "Facebook post",
    "threads": "Threads post",
    "linkedin": "LinkedIn post",
}


async def read(url: str) -> ReaderResult:
    canonical = canonicalize(url)
    name = platform(canonical.split("/")[2])
    pid = post_id(canonical) or ""
    handle = handle_from_url(canonical) or ""
    bits = [f"Platform: {LABELS.get(name, name)}"]
    if pid:
        bits.append(f"Post code: {pid}")
    if handle:
        bits.append(f"Handle in URL: @{handle}")
    return ReaderResult("web_search", "skipped", findings=" · ".join(bits))
