"""ENRICH: build the filing context in code (§7.4.1) and make the one Muse Spark call (§7.4.2).

Stable instructions come first (the prompt file); the variable blocks below come last.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from moira.ai import prompts
from moira.ai.client import LLM, InputPart
from moira.ai.prompts import escape
from moira.ai.schemas import EnrichOutput
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos import people as people_repo
from moira.db.repos.nuggets import Nugget
from moira.domain import timefmt
from moira.embed.model import Embedder
from moira.search import fts, vectors

USER_WORDS_MAX = 4000
FOUND_MAX = 4000
EXCERPT_MAX = 1500


@dataclass
class EnrichContext:
    text: str
    images: list[Path] = field(default_factory=list)
    candidate_hubs: dict[str, int] = field(default_factory=dict)  # public id → id
    shelves: dict[str, int] = field(default_factory=dict)
    similar: dict[str, int] = field(default_factory=dict)  # nugget public id → id
    people: dict[str, int] = field(default_factory=dict)  # person public id → id
    note: str = ""


def research_line(r: sqlite3.Row) -> str:
    method = {
        "web_search": "web search",
        "youtube_oembed": "YouTube",
        "github_api": "GitHub",
        "page_fetch": "the page",
        "image": "the screenshot",
        "video": "the video",
        "pdf": "the PDF",
        "asr": "the voice note",
    }.get(r["method"], r["method"])
    label = method
    if r["method"] == "web_search":
        label += " · verified" if r["verified"] == 1 else " · possible match"
    parts = [p for p in (r["title"], r["author"], r["findings"]) if p]
    excerpt = (r["excerpt"] or "")[:EXCERPT_MAX]
    if excerpt:
        parts.append(excerpt)
    return f"[{label}] " + " · ".join(parts)


def found_block(conn: sqlite3.Connection, n: Nugget) -> str:
    lines = [research_line(r) for r in repo.research_for(conn, n.id) if r["status"] == "ok"]
    if n.content_text:
        lines.append(f"[attachment] {n.content_text}")
    return escape("\n".join(lines))[:FOUND_MAX]


def hub_line(conn: sqlite3.Connection, hub_id: int) -> str:
    hub = hubs_repo.get(conn, hub_id)
    assert hub is not None
    members = hubs_repo.members(conn, hub_id)
    members.sort(key=lambda m: (m.role != "current", -(m.since or 0)))
    shown = []
    for m in members[:5]:
        n = repo.get(conn, m.nugget_id)
        e = repo.enrichment(conn, m.nugget_id)
        if n is None:
            continue
        title = escape(e["title"] if e else n.user_text[:60]).replace('"', "'")
        role = f" ({m.role})" if m.role in ("current", "earlier", "corrected") else ""
        shown.append(f'{n.public_id} "{title}"{role}')
    name = escape(hub.name).replace('"', "'")
    now = escape(hub.now_line).replace('"', "'")
    line = f'- id={hub.public_id} kind={hub.kind} name="{name}" now="{now}"'
    return line + (" members: " + "; ".join(shown) if shown else "")


def mentioned_people(conn: sqlite3.Connection, text: str) -> list[people_repo.Person]:
    words = {w.lower() for w in re.findall(r"[A-Za-z][\w'-]+", text)}
    words |= {w.removesuffix("'s") for w in words}
    found = []
    for p in people_repo.all_people(conn):
        names = [p.display_name, *p.aliases]
        if any(part.lower() in words for name in names for part in name.split()):
            found.append(p)
    return found[:10]


def build_context(
    conn: sqlite3.Connection,
    n: Nugget,
    *,
    now_ms: int,
    tz: str,
    embedder: Embedder | None,
    images: list[Path] | None = None,
    note: str = "",
) -> EnrichContext:
    ctx = EnrichContext(text="", images=list(images or [])[:10], note=note)
    words = n.user_text[:USER_WORDS_MAX]
    link_title = next(
        (r["title"] for r in repo.research_for(conn, n.id) if r["status"] == "ok" and r["title"]),
        "",
    )
    query_terms = fts.words(f"{words} {link_title}")[:30]

    # Candidate hubs: FTS on words + link title, hub-vector KNN, people named in the text.
    hub_ids: list[int] = []
    for hid in fts.search_hubs(conn, query_terms, 5):
        if hid not in hub_ids:
            hub_ids.append(hid)
    nugget_vec = vectors.get(conn, "vec_nuggets", n.id)
    if nugget_vec is None and embedder is not None and (words or link_title):
        nugget_vec = embedder.encode([f"{words} {link_title}"])[0]
    if nugget_vec is not None:
        for hid, _ in vectors.knn(conn, "vec_hubs", nugget_vec, 8):
            if hid not in hub_ids:
                hub_ids.append(hid)
    people = mentioned_people(conn, f"{words} {link_title}")
    for p in people:
        hub = hubs_repo.by_person(conn, p.id)
        if hub is not None and hub.id not in hub_ids:
            hub_ids.insert(0, hub.id)
    candidates = []
    for hid in hub_ids:
        hub = hubs_repo.get(conn, hid)
        if hub is None or hub.kind == "shelf" or hub.archived:
            continue
        candidates.append(hid)
        ctx.candidate_hubs[hub.public_id] = hid
        if len(candidates) >= 8:
            break
    for shelf in hubs_repo.shelves(conn):
        ctx.shelves[shelf.public_id] = shelf.id

    # Similar nuggets: vector KNN + FTS, excluding itself.
    similar: list[int] = []
    if nugget_vec is not None:
        similar += [
            nid for nid, _ in vectors.knn(conn, "vec_nuggets", nugget_vec, 12) if nid != n.id
        ]
    similar += [nid for nid in fts.search(conn, query_terms, 12) if nid != n.id]
    sim_lines = []
    for nid in dict.fromkeys(similar):
        other = repo.get(conn, nid)
        if other is None or other.deleted_at is not None:
            continue
        e = repo.enrichment(conn, nid)
        title = escape(e["title"] if e else other.user_text[:60]).replace('"', "'")
        hub_names = ", ".join(
            h.name
            for m in hubs_repo.memberships(conn, nid)
            if (h := hubs_repo.get(conn, m.hub_id)) is not None
        )
        when = timefmt.day_month_year(other.captured_at, tz)
        sim_lines.append(f'- id={other.public_id} "{title}" ({when}) hubs: {hub_names or "none"}')
        ctx.similar[other.public_id] = nid
        if len(sim_lines) >= 8:
            break

    # Recent context: the previous 3 nuggets.
    recent_lines = []
    prev = n
    for _ in range(3):
        before = repo.previous(conn, prev)
        if before is None:
            break
        e = repo.enrichment(conn, before.id)
        title = escape(e["title"] if e else before.user_text[:60]).replace('"', "'")
        recent_lines.append(f'- "{title}" ({timefmt.gap(before.captured_at, n.captured_at)})')
        prev = before

    people_lines = []
    for p in people:
        ctx.people[p.public_id] = p.id
        aliases = ", ".join(p.aliases)
        who = p.disambiguator
        people_lines.append(
            f'- id={p.public_id} name="{p.display_name}" aliases="{aliases}" who="{who}"'
        )

    attrs = [
        f'id="{n.public_id}"',
        f'source="{n.source}"',
        f'saved="{timefmt.full(n.captured_at, tz)}"',
    ]
    if n.url:
        attrs.append(f'url="{escape(n.url)}"')
    if n.forward_from:
        attrs.append(f'forwarded_from="{escape(n.forward_from)}"')
    if n.original_posted_at:
        attrs.append(f'originally_posted="{timefmt.full(n.original_posted_at, tz)}"')
    shelf_line = " · ".join(
        f"id={pid} {hubs_repo.get(conn, hid).name}"  # type: ignore[union-attr]
        for pid, hid in ctx.shelves.items()
    )
    blocks = [
        f"<now>{timefmt.full(now_ms, tz)} ({tz})</now>",
        f"<nugget {' '.join(attrs)}/>",
        f"<user_words>\n{escape(words)}\n</user_words>",
        f"<found_content>\n{found_block(conn, n)}\n</found_content>",
        "<recent_context>\n" + ("\n".join(recent_lines) or "(none)") + "\n</recent_context>",
        "<candidate_hubs>\n"
        + ("\n".join(hub_line(conn, hid) for hid in candidates) or "(none)")
        + "\n</candidate_hubs>",
        f"<shelves>\n- {shelf_line}\n</shelves>",
        "<similar_nuggets>\n" + ("\n".join(sim_lines) or "(none)") + "\n</similar_nuggets>",
        "<known_people>\n" + ("\n".join(people_lines) or "(none)") + "\n</known_people>",
    ]
    if note:
        blocks.append(f"<note>{escape(note)}</note>")
    ctx.text = "\n".join(blocks)
    return ctx


async def enrich(llm: LLM, ctx: EnrichContext, *, user_id: int | None) -> EnrichOutput:
    prompt = prompts.load("enrich")
    parts = [InputPart(text=ctx.text)]
    for path in ctx.images:
        parts.append(InputPart.image(path.read_bytes()))
    return await llm.structured(
        prompt=prompt,
        inputs=parts,
        schema=EnrichOutput,
        effort="low",
        max_output_tokens=1500,
        timeout_s=60,
        user_id=user_id,
        kind="enrich",
    )


def raw_json(out: EnrichOutput) -> str:
    return json.dumps(out.model_dump(), ensure_ascii=False)
