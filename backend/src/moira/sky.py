"""The sky payload (§7.7.4): columnar, compressed by Caddy, ~120 KB for 10,000 stars.

flags: 1 earlier, 2 corrected, 4 has research, 8 pinned, 16 sample. Colour comes from ``t``.
"""

import sqlite3
from typing import Any

FLAG_EARLIER, FLAG_CORRECTED, FLAG_RESEARCH, FLAG_PINNED, FLAG_SAMPLE = 1, 2, 4, 8, 16


def threads(conn: sqlite3.Connection, since: int | None = None) -> list[list[str]]:
    """[earlier, replacedBy] pairs: each replaced fact and what replaced it (same event group)."""
    rows = conn.execute(
        "SELECT e.group_id, e.hub_id, e.nugget_id, n.public_id FROM hub_events e"
        " JOIN nuggets n ON n.id = e.nugget_id WHERE e.event = 'role_changed' AND e.undone = 0"
        " AND json_extract(e.after_json, '$.role') IN ('earlier','corrected')"
        " AND n.deleted_at IS NULL"
    ).fetchall()
    out: list[list[str]] = []
    for r in rows:
        newer = conn.execute(
            "SELECT n.public_id FROM hub_events e JOIN nuggets n ON n.id = e.nugget_id"
            " WHERE e.group_id = ? AND e.hub_id = ? AND e.nugget_id <> ? AND e.undone = 0"
            " AND e.event IN ('member_added','role_changed')"
            " AND json_extract(e.after_json, '$.role') = 'current' AND n.deleted_at IS NULL"
            " LIMIT 1",
            (r["group_id"], r["hub_id"], r["nugget_id"]),
        ).fetchone()
        if newer is not None:
            pair = [r["public_id"], newer[0]]
            if pair not in out:
                out.append(pair)
    return out


def payload(conn: sqlite3.Connection, *, now_ms: int, since: int | None = None) -> dict[str, Any]:
    where = "n.deleted_at IS NULL"
    args: list[Any] = []
    if since is not None:
        where += " AND (n.updated_at > ? OR s.placed_at > ?)"
        args += [since, since]
    rows = conn.execute(
        "SELECT n.public_id, s.x, s.y, COALESCE(e.kind, 'note') AS kind, h.public_id AS hub,"  # noqa: S608
        " COALESCE(e.title, substr(n.user_text, 1, 60), 'Saved item') AS title,"
        " n.captured_at AS t, s.importance AS imp, n.pinned, n.is_sample, n.source,"
        " (SELECT GROUP_CONCAT(role) FROM hub_members m2 WHERE m2.nugget_id = n.id) AS roles,"
        " EXISTS(SELECT 1 FROM research r WHERE r.nugget_id = n.id AND r.status = 'ok') AS res"
        " FROM nuggets n JOIN stars s ON s.nugget_id = n.id"
        " LEFT JOIN enrichments e ON e.nugget_id = n.id"
        " LEFT JOIN hub_members m ON m.nugget_id = n.id AND m.is_primary = 1"
        " LEFT JOIN hubs h ON h.id = m.hub_id"
        f" WHERE {where} ORDER BY n.captured_at",
        args,
    ).fetchall()
    stars: dict[str, list[Any]] = {
        k: [] for k in ("id", "x", "y", "kind", "hub", "t", "imp", "flags", "title", "source")
    }
    for r in rows:
        roles = set((r["roles"] or "").split(","))
        flags = 0
        if "earlier" in roles and "current" not in roles:
            flags |= FLAG_EARLIER
        if "corrected" in roles and "current" not in roles:
            flags |= FLAG_CORRECTED
        if r["res"]:
            flags |= FLAG_RESEARCH
        if r["pinned"]:
            flags |= FLAG_PINNED
        if r["is_sample"]:
            flags |= FLAG_SAMPLE
        stars["id"].append(r["public_id"])
        stars["x"].append(round(r["x"], 1))
        stars["y"].append(round(r["y"], 1))
        stars["kind"].append(r["kind"])
        stars["hub"].append(r["hub"])
        stars["t"].append(r["t"])
        stars["imp"].append(round(r["imp"], 3))
        stars["flags"].append(flags)
        stars["title"].append((r["title"] or "Saved item")[:60])
        stars["source"].append(r["source"])
    hub_rows = conn.execute(
        "SELECT h.public_id, h.name, h.kind, h.x, h.y, h.now_line,"
        " (SELECT COUNT(*) FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id"
        "  WHERE m.hub_id = h.id AND n.deleted_at IS NULL) AS count"
        " FROM hubs h WHERE h.archived = 0 ORDER BY h.id"
    ).fetchall()
    hubs = [
        {
            "id": h["public_id"],
            "name": h["name"],
            "kind": h["kind"],
            "x": round(h["x"], 1),
            "y": round(h["y"], 1),
            "count": h["count"],
            "now": h["now_line"],
        }
        for h in hub_rows
    ]
    removed: list[str] = []
    if since is not None:
        removed = [
            r[0]
            for r in conn.execute(
                "SELECT public_id FROM nuggets WHERE deleted_at IS NOT NULL AND deleted_at > ?",
                (since,),
            )
        ]
    return {
        "v": 1,
        "cursor": str(now_ms),
        "stars": stars,
        "hubs": hubs,
        "threads": threads(conn),
        "removed": removed,
    }
