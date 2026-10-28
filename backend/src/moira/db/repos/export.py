"""Rows for the user's own export (App. B ``/api/export``, §13.14 weekly export)."""

import sqlite3


def nuggets_since(conn: sqlite3.Connection, since: int | None) -> list[sqlite3.Row]:
    """Live nuggets (new or changed since ``since``), with title, kind and constellations."""
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT n.public_id, n.source, n.user_text, n.content_text, n.url, n.captured_at,"
        " n.captured_tz, n.updated_at, n.version, e.title, e.summary, e.kind,"
        " (SELECT json_group_array(h.name) FROM hub_members m JOIN hubs h ON h.id = m.hub_id"
        "   WHERE m.nugget_id = n.id AND h.archived = 0) AS hubs"
        " FROM nuggets n LEFT JOIN enrichments e ON e.nugget_id = n.id"
        " WHERE n.deleted_at IS NULL AND (? IS NULL OR n.updated_at > ?)"
        " ORDER BY n.captured_at",
        (since, since),
    ).fetchall()
    return rows
