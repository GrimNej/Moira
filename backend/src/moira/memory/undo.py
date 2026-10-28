"""Undo (§7.12): revert an event group by applying ``before_json`` states in reverse order.

Event payload conventions (written by filing, forget, move and tidy):

| event | before_json / after_json |
|---|---|
| member_added | after: the membership |
| member_removed | before: the membership |
| role_changed | before/after: {role, until} |
| now_changed | before/after: {now_line} |
| hub_created | after: {name} (undo archives the hub when it has no members left) |
| hub_renamed | before/after: {name, name_norm} |
| hub_merged | before: {archived, merged_into} |
| moved | before/after: {primary_hub_id} |
| forgotten | before: {deleted_at: null} |
| restored | before/after: roles swapped (recorded as role_changed rows in the same group) |
"""

import json
import sqlite3

from moira import ids
from moira.db.repos import events
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as nuggets_repo
from moira.logging import get_logger

log = get_logger(__name__)


def new_group(prefix: str) -> str:
    return f"{prefix}:{ids.new('t_')[2:]}"


def _revert(conn: sqlite3.Connection, row: sqlite3.Row, now: int) -> None:
    ev = row["event"]
    hub_id, nugget_id = row["hub_id"], row["nugget_id"]
    before = json.loads(row["before_json"]) if row["before_json"] else {}
    if ev == "member_added" and hub_id and nugget_id:
        hubs_repo.remove_member(conn, hub_id, nugget_id)
    elif ev == "member_removed" and hub_id and nugget_id:
        hubs_repo.add_member(
            conn,
            hub_id=hub_id,
            nugget_id=nugget_id,
            role=before.get("role", "member"),
            since=before.get("since", now),
            until=before.get("until"),
            decided_by=before.get("decided_by", "user"),
            is_primary=bool(before.get("is_primary", False)),
            confidence=before.get("confidence"),
            evidence=before.get("evidence", ""),
        )
    elif ev == "role_changed" and hub_id and nugget_id:
        if hubs_repo.member(conn, hub_id, nugget_id) is not None:
            hubs_repo.set_role(
                conn,
                hub_id,
                nugget_id,
                before["role"],
                before.get("until"),
                before.get("decided_by", "user"),
            )
    elif ev == "now_changed" and hub_id:
        hubs_repo.set_now_line(conn, hub_id, before.get("now_line", ""), now)
    elif ev == "hub_created" and hub_id:
        if hubs_repo.member_count(conn, hub_id) == 0:
            hubs_repo.set_archived(conn, hub_id, True, now, None)
    elif ev == "hub_renamed" and hub_id:
        hubs_repo.rename(conn, hub_id, before["name"], before["name_norm"], now)
    elif ev == "hub_merged" and hub_id:
        hubs_repo.set_archived(
            conn, hub_id, bool(before.get("archived")), now, before.get("merged_into")
        )
    elif ev == "moved" and nugget_id and before.get("primary_hub_id"):
        hubs_repo.set_primary(conn, nugget_id, before["primary_hub_id"])
    elif ev == "forgotten" and nugget_id:
        n = nuggets_repo.get(conn, nugget_id)
        if n is not None:
            nuggets_repo.restore_deleted(conn, nugget_id, now)


def undo_group(conn: sqlite3.Connection, group_id: str, *, now: int, actor: str = "user") -> bool:
    """Revert one group. Returns False if it does not exist or was already undone."""
    rows = events.group(conn, group_id)
    if not rows or all(r["undone"] for r in rows):
        return False
    for row in reversed(rows):
        if not row["undone"]:
            _revert(conn, row, now)
    events.mark_undone(conn, group_id)
    events.record(
        conn,
        group_id=f"undo:{group_id}",
        event="undone",
        actor=actor,
        now=now,
        after={"group_id": group_id},
    )
    _ensure_primary(conn, {r["nugget_id"] for r in rows if r["nugget_id"]}, now)
    log.info("undone", events=len(rows))
    return True


def _ensure_primary(conn: sqlite3.Connection, nugget_ids: set[int], now: int) -> None:
    """Principle 6 after an undo: a filed nugget falls back to its shelf (§7.12)."""
    from moira.memory.shelf import fallback_shelf

    for nid in nugget_ids:
        n = nuggets_repo.get(conn, nid)
        if n is None or n.deleted_at is not None or n.status != "filed":
            continue
        members = hubs_repo.memberships(conn, nid)
        if not members:
            shelf = fallback_shelf(conn, nid)
            hubs_repo.add_member(
                conn,
                hub_id=shelf.id,
                nugget_id=nid,
                role="member",
                since=now,
                decided_by="code",
                is_primary=True,
            )
        elif not any(m.is_primary for m in members):
            hubs_repo.set_primary(conn, nid, members[0].hub_id)


def undo_latest(
    conn: sqlite3.Connection, *, now: int, actors: tuple[str, ...] = ("ai",)
) -> str | None:
    group_id = events.latest_undoable_group(conn, actors)
    if group_id is None:
        return None
    return group_id if undo_group(conn, group_id, now=now) else None
