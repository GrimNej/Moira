"""ANSWER (§8.3, §9.8.3): answer only from the candidates; every claim cites one."""

import json
import sqlite3

from moira.ai import prompts
from moira.ai.client import LLM, InputPart
from moira.ai.prompts import escape
from moira.ai.schemas import AnswerOutput
from moira.capture.urls import platform
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.domain import timefmt

SOURCE_LABELS = {
    "typed": "you typed it",
    "voice": "a voice note",
    "screenshot": "a screenshot",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "github": "GitHub",
    "web": "a web page",
    "x": "X",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "threads": "Threads",
    "video": "a video",
    "forward": "a forwarded message",
    "location": "a location",
    "contact": "a contact",
    "other": "a file",
}


def q(s: str, n: int) -> str:
    return escape(" ".join(s.split()))[:n].replace('"', "'")


def candidate_line(conn: sqlite3.Connection, idx: int, nid: int, now_ms: int, tz: str) -> str:
    n = repo.get(conn, nid)
    assert n is not None
    e = repo.enrichment(conn, nid)
    found = []
    for r in repo.research_for(conn, nid):
        if r["status"] != "ok":
            continue
        label = r["method"].replace("_", " ")
        if r["method"] == "web_search":
            label = "web search · " + ("verified" if r["verified"] == 1 else "possible")
        found.append(f"[{label}] " + " ".join(p for p in (r["title"], r["findings"]) if p))
    if n.content_text:
        found.append(f"[attachment] {n.content_text}")
    hubs = []
    now_lines = []
    for m in hubs_repo.memberships(conn, nid):
        h = hubs_repo.get(conn, m.hub_id)
        if h is None:
            continue
        hubs.append(f"{h.name} ({m.role})")
        if h.kind in ("fact", "person") and h.now_line:
            now_lines.append(f"{h.name}: {h.now_line}")
    parts = [
        f"[{idx}] id={n.public_id}",
        f'saved="{timefmt.full(n.captured_at, n.captured_tz or tz)}"',
        f"({timefmt.relative(n.captured_at, now_ms, tz)})",
        f'source="{SOURCE_LABELS.get(n.source, n.source)}"',
        f"kind={e['kind'] if e else 'note'}",
        f'title="{q(e["title"] if e else n.user_text, 100)}"',
    ]
    if e is not None:
        parts.append(f'summary="{q(e["summary"], 200)}"')
    parts.append(f'you_wrote="{q(n.user_text, 300)}"')
    if found:
        parts.append(f'found="{q(" ".join(found), 300)}"')
    if e is not None and e["guess"]:
        parts.append(f'guess="{q(e["guess"], 150)}"')
    if e is not None and e["structured_list"]:
        lst = json.loads(e["structured_list"])
        parts.append(f'list="{q(", ".join(lst.get("items", [])), 200)}"')
    if hubs:
        parts.append(f'hubs="{q("; ".join(hubs), 160)}"')
    if now_lines:
        parts.append(f'now="{q("; ".join(now_lines), 200)}"')
    if n.url:
        parts.append(f'link="{platform(n.url.split("/")[2]) if "//" in n.url else "web"}"')
    return " ".join(parts)


async def answer(
    llm: LLM,
    *,
    question: str,
    now_text: str,
    clues: str,
    conversation: str,
    candidates: list[str],
    extra: str = "",
    user_id: int | None,
) -> AnswerOutput:
    blocks = [
        f"<now>{now_text}</now>",
        f"<question>{escape(question)}</question>",
        f"<clues>{escape(clues)}</clues>",
        f"<conversation>\n{conversation or '(none)'}\n</conversation>",
    ]
    if extra:
        blocks.append(extra)
    blocks.append("<candidates>\n" + ("\n".join(candidates) or "(none)") + "\n</candidates>")
    return await llm.structured(
        prompt=prompts.load("answer"),
        inputs=[InputPart(text="\n".join(blocks))],
        schema=AnswerOutput,
        effort="low",
        max_output_tokens=700,
        timeout_s=30,
        user_id=user_id,
        kind="answer",
    )
