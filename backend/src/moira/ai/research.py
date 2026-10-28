"""RESEARCH (§7.5): web search for a bare or walled link, verified in code, never scraped.

``verified`` is decided by code: a cited or result URL must contain the platform post id
(or equal the canonical URL). The model's own MATCH line is only a hint.
"""

import re
from dataclasses import dataclass, field

from moira.ai import prompts
from moira.ai.client import LLM
from moira.capture.urls import canonicalize, handle_from_url, platform, post_id

LABELS = {
    "instagram": "Instagram reel",
    "x": "Post on X",
    "tiktok": "TikTok video",
    "facebook": "Facebook post",
    "threads": "Threads post",
    "linkedin": "LinkedIn post",
    "youtube": "YouTube video",
    "github": "GitHub page",
    "web": "Web page",
}
FIELD = re.compile(r"^(CREATOR|TITLE|TOPIC|SUMMARY|MATCH):\s*(.*)$", re.M)


@dataclass
class ResearchResult:
    status: str  # ok | not_found
    verified: bool | None
    title: str = ""
    author: str = ""
    findings: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    searches: int = 0


def query_text(url: str, note: str) -> str:
    canonical = canonicalize(url)
    name = platform(canonical.split("/")[2])
    pid = post_id(canonical)
    handle = handle_from_url(canonical)
    rest = note.replace(url, "").strip()
    return "\n".join(
        [
            f"Post URL: {canonical}",
            f"Platform: {LABELS.get(name, 'Web page')}",
            f"Post code: {pid or '(none)'}",
            f"Handle in URL: {'@' + handle if handle else '(none)'}",
            f"The person's note: {rest or '(none)'}",
        ]
    )


def parse(text: str) -> dict[str, str]:
    out = {k.lower(): v.strip() for k, v in FIELD.findall(text)}
    return {k: ("" if v.lower() == "unknown" else v) for k, v in out.items()}


def verify(url: str, sources: list[dict[str, str]]) -> bool:
    canonical = canonicalize(url)
    pid = post_id(canonical)
    for s in sources:
        found = s.get("url", "")
        if not found:
            continue
        try:
            c = canonicalize(found)
        except ValueError:
            continue
        if c == canonical or (pid and pid in c) or (pid and pid in found):
            return True
    return False


async def research(llm: LLM, url: str, note: str, *, user_id: int | None) -> ResearchResult:
    raw = await llm.research(
        prompt=prompts.load("research"), text=query_text(url, note), user_id=user_id
    )
    fields = parse(raw.text)
    match = fields.get("match", "").lower()
    if match.startswith("not_found") or not any(
        fields.get(k) for k in ("title", "topic", "summary")
    ):
        return ResearchResult("not_found", None, sources=raw.sources, searches=raw.searches)
    verified = verify(url, raw.sources)
    bits = []
    if fields.get("creator"):
        bits.append(f"CREATOR: {fields['creator']}")
    if fields.get("topic"):
        bits.append(f"TOPIC: {fields['topic']}")
    if fields.get("summary"):
        bits.append(f"SUMMARY: {fields['summary']}")
    return ResearchResult(
        "ok",
        verified,
        title=fields.get("title", "") or fields.get("topic", ""),
        author=fields.get("creator", ""),
        findings=" · ".join(bits),
        sources=raw.sources[:8],
        searches=raw.searches,
    )
