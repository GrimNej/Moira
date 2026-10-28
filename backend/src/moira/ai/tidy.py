"""Nightly tidy (§7.9): merge near-duplicate constellations and fix unclear names.

The model only proposes; code applies a change when the gates pass, at most 5 per night.
Every change is one undoable event group; stars do not move.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from html import escape

import numpy as np

from moira.ai import prompts
from moira.ai.client import LLM, InputPart
from moira.ai.schemas import TidyOutput
from moira.db.repos import events
from moira.db.repos import hubs as hubs_repo
from moira.db.repos.hubs import Hub
from moira.domain.text import name_norm as normalize_name
from moira.embed.model import Embedder
from moira.memory.undo import new_group

MAX_CHANGES = 5
MERGE_CONFIDENCE = 0.85
RENAME_CONFIDENCE = 0.9
NAME_SIMILARITY = 0.6
VECTOR_COSINE = 0.85


@dataclass
class Change:
    kind: str  # merge | rename
    text: str  # "Merged “PC fixes” into “PC setup fixes”" (names only, never content)
    group_id: str


def candidates(conn: sqlite3.Connection) -> list[Hub]:
    return [h for h in hubs_repo.active(conn) if h.kind != "shelf"]


def build_input(conn: sqlite3.Connection, hubs: list[Hub]) -> str:
    counts = hubs_repo.counts(conn)
    lines = []
    for h in hubs:
        titles = hubs_repo.recent_member_titles(conn, h.id, limit=5)
        made = datetime.fromtimestamp(h.created_at / 1000, UTC).date().isoformat()
        lines.append(
            f'<hub id="{h.public_id}" kind="{h.kind}" members="{counts.get(h.id, 0)}" '
            f'created="{made}">\n<name>{escape(h.name)}</name>\n'
            + "\n".join(f"<item>{escape(t)}</item>" for t in titles)
            + "\n</hub>"
        )
    return "<hubs>\n" + "\n".join(lines) + "\n</hubs>"


async def propose(
    llm: LLM, conn: sqlite3.Connection, hubs: list[Hub], user_id: int | None
) -> TidyOutput:
    return await llm.structured(
        prompt=prompts.load("tidy"),
        inputs=[InputPart(text=build_input(conn, hubs))],
        schema=TidyOutput,
        effort="medium",
        max_output_tokens=1200,
        timeout_s=90,
        user_id=user_id,
        kind="tidy",
    )


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_name(a), normalize_name(b)).ratio()


def cosine(embedder: Embedder | None, a: str, b: str) -> float:
    if embedder is None:
        return 0.0
    v = embedder.encode([a, b])
    return float(np.dot(v[0], v[1]))  # rows are unit length


def _merge(conn: sqlite3.Connection, keep: Hub, other: Hub, group: str, now: int) -> None:
    for m in hubs_repo.members(conn, other.id):
        state = {
            "role": m.role,
            "since": m.since,
            "until": m.until,
            "decided_by": m.decided_by,
            "is_primary": m.is_primary,
            "confidence": m.confidence,
            "evidence": m.evidence,
        }
        if hubs_repo.member(conn, keep.id, m.nugget_id) is None:
            hubs_repo.add_member(
                conn,
                hub_id=keep.id,
                nugget_id=m.nugget_id,
                role=m.role,
                since=m.since,
                until=m.until,
                decided_by="ai",
                is_primary=m.is_primary,
                confidence=m.confidence,
                evidence=m.evidence,
            )
            events.record(
                conn, group_id=group, event="member_added", actor="ai", now=now,
                hub_id=keep.id, nugget_id=m.nugget_id, after=state,
            )  # fmt: skip
        hubs_repo.remove_member(conn, other.id, m.nugget_id)
        events.record(
            conn, group_id=group, event="member_removed", actor="ai", now=now,
            hub_id=other.id, nugget_id=m.nugget_id, before=state,
        )  # fmt: skip
    hubs_repo.set_archived(conn, other.id, True, now, keep.id)
    events.record(
        conn, group_id=group, event="hub_merged", actor="ai", now=now, hub_id=other.id,
        before={"archived": False, "merged_into": None}, after={"merged_into": keep.public_id},
    )  # fmt: skip


def _rename(conn: sqlite3.Connection, hub: Hub, name: str, group: str, now: int) -> None:
    norm = normalize_name(name)
    hubs_repo.rename(conn, hub.id, name, norm, now)
    events.record(
        conn, group_id=group, event="hub_renamed", actor="ai", now=now, hub_id=hub.id,
        before={"name": hub.name, "name_norm": hub.name_norm},
        after={"name": name, "name_norm": norm},
    )  # fmt: skip


def apply(
    conn: sqlite3.Connection,
    out: TidyOutput,
    hubs: list[Hub],
    *,
    now: int,
    embedder: Embedder | None,
) -> list[Change]:
    """Apply the proposals that pass the §7.9 gates, at most ``MAX_CHANGES``."""
    by_id = {h.public_id: h for h in hubs}
    gone: set[str] = set()
    changes: list[Change] = []
    with conn:
        for mg in sorted(out.merges, key=lambda m: -m.confidence):
            keep = by_id.get(mg.keep_hub_id)
            if keep is None or keep.public_id in gone or mg.confidence < MERGE_CONFIDENCE:
                continue
            for oid in mg.merge_hub_ids:
                other = by_id.get(oid)
                if len(changes) >= MAX_CHANGES:
                    break
                if other is None or other.id == keep.id or oid in gone:
                    continue
                if other.kind != keep.kind or keep.kind == "person":
                    continue  # never merge different kinds or different people
                close = name_similarity(keep.name, other.name) >= NAME_SIMILARITY or (
                    cosine(embedder, keep.name, other.name) >= VECTOR_COSINE
                )
                if not close:
                    continue
                group = new_group("tidy")
                _merge(conn, keep, other, group, now)
                gone.add(oid)
                changes.append(Change("merge", f"Merged “{other.name}” into “{keep.name}”", group))
        for rn in sorted(out.renames, key=lambda r: -r.confidence):
            if len(changes) >= MAX_CHANGES:
                break
            hub = by_id.get(rn.hub_id)
            name = rn.new_name.strip()
            if hub is None or rn.hub_id in gone or rn.confidence < RENAME_CONFIDENCE:
                continue
            if not name or len(name) > 40 or normalize_name(name) == hub.name_norm:
                continue
            if hub.kind == "person":
                continue  # people keep the name the user gave them
            group = new_group("tidy")
            _rename(conn, hub, name, group, now)
            gone.add(rn.hub_id)
            changes.append(Change("rename", f"Renamed “{hub.name}” to “{name}”", group))
    return changes
