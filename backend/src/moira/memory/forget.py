"""Forget (§7.11): soft delete with a 10-minute undo, then a real delete.

The Now line rebuild after a hard delete takes a ``rebuild_now`` callable so the AI layer
(NOW prompt, §9.8.6) stays out of this module; without one, the Now line is rebuilt in code
from the remaining current members' titles.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from moira.db.repos import events
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos.nuggets import Nugget
from moira.logging import get_logger
from moira.memory import indexing
from moira.memory.undo import new_group

log = get_logger(__name__)

UNDO_MS = 10 * 60_000
RebuildNow = Callable[[sqlite3.Connection, int], str]


@dataclass(frozen=True, slots=True)
class Forgotten:
    group_id: str
    undo_until: int
    nugget: Nugget


def soft_forget(conn: sqlite3.Connection, nugget: Nugget, *, now: int) -> Forgotten:
    group_id = new_group(f"forget:{nugget.public_id}")
    conn.execute("BEGIN IMMEDIATE")
    try:
        repo.soft_delete(conn, nugget.id, now)
        events.record(
            conn,
            group_id=group_id,
            event="forgotten",
            actor="user",
            now=now,
            nugget_id=nugget.id,
            before={"deleted_at": None},
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return Forgotten(group_id, now + UNDO_MS, nugget)


def default_now_line(conn: sqlite3.Connection, hub_id: int) -> str:
    current = hubs_repo.members(conn, hub_id, ("current",))
    titles = []
    for m in current:
        e = repo.enrichment(conn, m.nugget_id)
        if e is not None:
            titles.append(str(e["title"]))
    return "; ".join(titles)[:200]


def hard_delete(
    conn: sqlite3.Connection, nugget_id: int, *, now: int, rebuild_now: RebuildNow | None = None
) -> bool:
    """Delete for real (cascades) and repair the fact hubs it was part of."""
    n = repo.get(conn, nugget_id)
    if n is None or n.deleted_at is None:
        return False  # restored by Undo, or already gone
    rebuild = rebuild_now or default_now_line
    group_id = new_group(f"forget:{n.public_id}")
    affected = [m for m in hubs_repo.memberships(conn, nugget_id)]
    conn.execute("BEGIN IMMEDIATE")
    try:
        indexing.unindex(conn, nugget_id)
        repo.hard_delete(conn, nugget_id)
        for m in affected:
            hub = hubs_repo.get(conn, m.hub_id)
            if hub is None or hub.kind == "shelf":
                continue
            if hubs_repo.member_count(conn, hub.id) == 0:
                hubs_repo.set_archived(conn, hub.id, True, now, None)
                continue
            if hub.kind in ("fact", "person") and m.role == "current":
                if not hubs_repo.members(conn, hub.id, ("current",)):
                    earlier = hubs_repo.members(conn, hub.id, ("earlier",))
                    if earlier:
                        latest = max(earlier, key=lambda x: x.until or 0)
                        hubs_repo.set_role(conn, hub.id, latest.nugget_id, "current", None, "code")
                line = rebuild(conn, hub.id)
                if line != hub.now_line:
                    hubs_repo.set_now_line(conn, hub.id, line, now)
            indexing.index_hub(conn, hub.id, None)
        events.record(conn, group_id=group_id, event="forgotten", actor="code", now=now)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    log.info("hard_deleted")
    return True
