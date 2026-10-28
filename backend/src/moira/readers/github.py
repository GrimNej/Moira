"""GitHub reader: repo metadata, README excerpt, or a blob via raw.githubusercontent (§7.3.2)."""

import os
import re
from urllib.parse import urlsplit

import httpx

from moira.readers.base import BLOCKED_STATUS, ReaderResult

API = "https://api.github.com"
RAW_LIMIT = 100 * 1024


def _headers(raw: bool = False) -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
        "User-Agent": "Moira",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


async def read(canonical: str) -> ReaderResult:
    parts = urlsplit(canonical)
    segs = [s for s in parts.path.split("/") if s]
    host = (parts.hostname or "").lower()
    if host == "raw.githubusercontent.com" or (len(segs) >= 4 and segs[2] == "blob"):
        return await _blob(canonical, host, segs)
    if host == "gist.github.com" or len(segs) < 2:
        return ReaderResult("github_api", "skipped")
    owner, repo = segs[0], segs[1]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0)) as client:
            r = await client.get(f"{API}/repos/{owner}/{repo}", headers=_headers())
            if r.status_code in BLOCKED_STATUS:
                return ReaderResult("github_api", "blocked")
            if r.status_code == 404:
                return ReaderResult("github_api", "not_found")
            if r.status_code != 200:
                return ReaderResult("github_api", "error")
            data = r.json()
            readme = await client.get(f"{API}/repos/{owner}/{repo}/readme", headers=_headers(True))
            excerpt = readme.text[:4000] if readme.status_code == 200 else ""
    except httpx.HTTPError:
        return ReaderResult("github_api", "error")
    bits = [
        str(data.get("description") or ""),
        "Topics: " + ", ".join(data.get("topics") or []) if data.get("topics") else "",
        f"Language: {data['language']}" if data.get("language") else "",
        f"{data.get('stargazers_count', 0)} stars",
        f"Homepage: {data['homepage']}" if data.get("homepage") else "",
    ]
    return ReaderResult(
        "github_api",
        "ok",
        title=f"{owner}/{repo}",
        author=owner,
        findings=". ".join(b for b in bits if b),
        excerpt=excerpt,
        sources=[{"url": canonical, "title": f"{owner}/{repo}"}],
    )


async def _blob(canonical: str, host: str, segs: list[str]) -> ReaderResult:
    if host == "raw.githubusercontent.com":
        raw_url = canonical.split("#", 1)[0]
        path = "/".join(segs[3:])
    else:
        owner, repo, _, ref, *rest = segs
        path = "/".join(rest)
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=4.0)) as client:
            r = await client.get(raw_url, headers={"User-Agent": "Moira"})
    except httpx.HTTPError:
        return ReaderResult("github_api", "error")
    if r.status_code != 200:
        return ReaderResult("github_api", "blocked" if r.status_code in BLOCKED_STATUS else "error")
    text = r.content[:RAW_LIMIT].decode("utf-8", "replace")
    lines = re.search(r"#L(\d+)(?:-L(\d+))?$", canonical)
    if lines:
        a = int(lines.group(1))
        b = int(lines.group(2) or a)
        text = "\n".join(text.splitlines()[a - 1 : b])
    return ReaderResult(
        "github_api",
        "ok",
        title=path,
        findings=f"File {path} on GitHub.",
        excerpt=text[:3000],
        sources=[{"url": canonical, "title": path}],
    )
