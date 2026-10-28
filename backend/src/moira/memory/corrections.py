"""User corrections from the card (§4.3.6): Move, Unlink, Restore, Split. All undoable.

Each writes hub events with ``actor='user'`` in one group. Stars never move (stable sky).
"""

import sqlite3

from moira import ids
from moira.db.repos import events
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos.nuggets import Nugget
from moira.domain.text import name_norm
from moira.embed.model import Embedder
from moira.errors import NotFound, ValidationFailed
from moira.memory import indexing
from moira.memory.forget import default_now_line
from moira.memory.placement import place_hub_center
from moira.memory.shelf import fallback_shelf
from moira.memory.undo import new_group


def _member_after(conn: sqlite3.Connection, hub_id: int, nugget_id: int) -> dict[str, object]:
    m = hubs_repo.member(conn, hub_id, nugget_id)
    assert m is not None
    return {
        "role": m.role,
        "is_primary": m.is_primary,
        "since": m.since,
        "until": m.until,
        "decided_by": m.decided_by,
        "confidence": m.confidence,
        "evidence": m.evidence,
    }


def move(
    conn: sqlite3.Connection,
    n: Nugget,
    *,
    hub_public_id: str | None,
    new_hub_name: str | None,
    now: int,
    embedder: Embedder | None,
) -> str:
    group = new_group(f"move:{n.public_id}")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if hub_public_id:
            hub = hubs_repo.by_public_id(conn, hub_public_id)
            if hub is None or hub.archived:
                raise NotFound("No such constellation.")
        elif new_hub_name and new_hub_name.strip():
            name = new_hub_name.strip()[:40]
            hub = hubs_repo.by_name_norm(conn, name_norm(name))
            if hub is None:
                pid = ids.new("h_")
                prim = hubs_repo.primary_hub(conn, n.id)
                anchor = (prim.x, prim.y) if prim else (0.0, 0.0)
                x, y = place_hub_center(conn, anchor, pid)
                hub = hubs_repo.create(
                    conn,
                    public_id=pid,
                    name=name,
                    name_norm=name_norm(name),
                    kind="topic",
                    x=x,
                    y=y,
                    now=now,
                )
                events.record(
                    conn,
                    group_id=group,
                    event="hub_created",
                    actor="user",
                    now=now,
                    hub_id=hub.id,
                    after={"name": name},
                )
        else:
            raise ValidationFailed("Pick a constellation or name a new one.")
        old_primary = hubs_repo.primary_hub(conn, n.id)
        if hubs_repo.member(conn, hub.id, n.id) is None:
            hubs_repo.add_member(
                conn, hub_id=hub.id, nugget_id=n.id, role="member", since=now, decided_by="user"
            )
            events.record(
                conn,
                group_id=group,
                event="member_added",
                actor="user",
                now=now,
                hub_id=hub.id,
                nugget_id=n.id,
                after=_member_after(conn, hub.id, n.id),
            )
        hubs_repo.set_primary(conn, n.id, hub.id)
        events.record(
            conn,
            group_id=group,
            event="moved",
            actor="user",
            now=now,
            nugget_id=n.id,
            hub_id=hub.id,
            before={"primary_hub_id": old_primary.id if old_primary else None},
            after={"primary_hub_id": hub.id},
        )
        indexing.index_full(conn, n.id, embedder)
        indexing.index_hub(conn, hub.id, embedder)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return group


def unlink(
    conn: sqlite3.Connection, n: Nugget, *, hub_public_id: str, now: int, embedder: Embedder | None
) -> str:
    hub = hubs_repo.by_public_id(conn, hub_public_id)
    if hub is None:
        raise NotFound("No such constellation.")
    m = hubs_repo.member(conn, hub.id, n.id)
    if m is None:
        raise NotFound("It is not in that constellation.")
    group = new_group(f"unlink:{n.public_id}")
    conn.execute("BEGIN IMMEDIATE")
    try:
        before = _member_after(conn, hub.id, n.id)
        hubs_repo.remove_member(conn, hub.id, n.id)
        events.record(
            conn,
            group_id=group,
            event="member_removed",
            actor="user",
            now=now,
            hub_id=hub.id,
            nugget_id=n.id,
            before=before,
        )
        remaining = hubs_repo.memberships(conn, n.id)
        if not remaining:  # principle 6: fall back to its shelf
            shelf = fallback_shelf(conn, n.id)
            if shelf.id == hub.id:
                raise ValidationFailed("It needs at least one constellation.")
            hubs_repo.add_member(
                conn,
                hub_id=shelf.id,
                nugget_id=n.id,
                role="member",
                since=now,
                decided_by="user",
                is_primary=True,
            )
            events.record(
                conn,
                group_id=group,
                event="member_added",
                actor="user",
                now=now,
                hub_id=shelf.id,
                nugget_id=n.id,
                after=_member_after(conn, shelf.id, n.id),
            )
        elif m.is_primary:
            hubs_repo.set_primary(conn, n.id, remaining[0].hub_id)
            events.record(
                conn,
                group_id=group,
                event="moved",
                actor="user",
                now=now,
                nugget_id=n.id,
                before={"primary_hub_id": hub.id},
                after={"primary_hub_id": remaining[0].hub_id},
            )
        indexing.index_full(conn, n.id, embedder)
        indexing.index_hub(conn, hub.id, embedder)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return group


def restore(conn: sqlite3.Connection, n: Nugget, *, now: int, embedder: Embedder | None) -> str:
    """An Earlier row becomes current again; what replaced it becomes Earlier (§7.12)."""
    group = new_group(f"restore:{n.public_id}")
    changed = False
    conn.execute("BEGIN IMMEDIATE")
    try:
        for m in hubs_repo.memberships(conn, n.id):
            if m.role not in ("earlier", "corrected"):
                continue
            hub = hubs_repo.get(conn, m.hub_id)
            if hub is None:
                continue
            for cur in hubs_repo.members(conn, hub.id, ("current",)):
                if cur.nugget_id == n.id:
                    continue
                hubs_repo.set_role(conn, hub.id, cur.nugget_id, "earlier", now, "user")
                events.record(
                    conn,
                    group_id=group,
                    event="role_changed",
                    actor="user",
                    now=now,
                    hub_id=hub.id,
                    nugget_id=cur.nugget_id,
                    before={"role": "current", "until": None, "decided_by": cur.decided_by},
                    after={"role": "earlier", "until": now},
                )
            hubs_repo.set_role(conn, hub.id, n.id, "current", None, "user")
            events.record(
                conn,
                group_id=group,
                event="role_changed",
                actor="user",
                now=now,
                hub_id=hub.id,
                nugget_id=n.id,
                before={"role": m.role, "until": m.until, "decided_by": m.decided_by},
                after={"role": "current", "until": None},
            )
            line = default_now_line(conn, hub.id) or hub.now_line
            if line != hub.now_line:
                hubs_repo.set_now_line(conn, hub.id, line, now)
                events.record(
                    conn,
                    group_id=group,
                    event="now_changed",
                    actor="user",
                    now=now,
                    hub_id=hub.id,
                    before={"now_line": hub.now_line},
                    after={"now_line": line},
                )
            indexing.index_hub(conn, hub.id, embedder)
            changed = True
        if not changed:
            raise ValidationFailed("This memory is already current.")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return group


def split(
    conn: sqlite3.Connection,
    n: Nugget,
    parts: list[list[int]],
    *,
    now: int,
    embedder: Embedder | None,
) -> list[Nugget]:
    """Split a merged capture group: every part after the first becomes its own memory."""
    raws = {r["id"]: r for r in repo.raw_events_for(conn, n.id) if r["edit_of"] is None}
    if len(parts) < 2 or any(not p for p in parts) or any(r not in raws for p in parts for r in p):
        raise ValidationFailed("Each part needs at least one of this memory's messages.")
    created: list[Nugget] = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        keep_text = "\n".join(raws[r]["text"] or "" for r in parts[0]).strip()
        for part in parts[1:]:
            text = "\n".join(raws[r]["text"] or "" for r in part).strip()
            first = raws[part[0]]
            new = repo.insert(
                conn,
                public_id=ids.new("n_"),
                source=n.source if not text else "typed",
                user_text=text,
                captured_at=first["received_at"],
                captured_tz=n.captured_tz,
                now=now,
            )
            for r in part:
                repo.link_raw_event(conn, r, new.id)
            indexing.index_instant(conn, new.id, embedder)
            created.append(new)
        if keep_text != n.user_text:
            repo.add_version(conn, n.id, keep_text, "web_edit", now)
        indexing.index_instant(conn, n.id, embedder)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return created
