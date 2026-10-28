"""Hubs (constellations) and their members (§6.3). Hubs link nuggets; they never merge them."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Hub:
    id: int
    public_id: str
    name: str
    name_norm: str
    kind: str
    now_line: str
    x: float
    y: float
    person_id: int | None
    archived: bool
    merged_into: int | None
    created_at: int
    updated_at: int


@dataclass(frozen=True, slots=True)
class Member:
    hub_id: int
    nugget_id: int
    role: str
    is_primary: bool
    since: int
    until: int | None
    decided_by: str
    confidence: float | None
    evidence: str


def _hub(row: sqlite3.Row | None) -> Hub | None:
    if row is None:
        return None
    return Hub(
        id=row["id"],
        public_id=row["public_id"],
        name=row["name"],
        name_norm=row["name_norm"],
        kind=row["kind"],
        now_line=row["now_line"],
        x=row["x"],
        y=row["y"],
        person_id=row["person_id"],
        archived=bool(row["archived"]),
        merged_into=row["merged_into"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _member(row: sqlite3.Row) -> Member:
    return Member(
        hub_id=row["hub_id"],
        nugget_id=row["nugget_id"],
        role=row["role"],
        is_primary=bool(row["is_primary"]),
        since=row["since"],
        until=row["until"],
        decided_by=row["decided_by"],
        confidence=row["confidence"],
        evidence=row["evidence"],
    )


def create(
    conn: sqlite3.Connection,
    *,
    public_id: str,
    name: str,
    name_norm: str,
    kind: str,
    x: float,
    y: float,
    now: int,
    person_id: int | None = None,
    now_line: str = "",
) -> Hub:
    cur = conn.execute(
        "INSERT INTO hubs(public_id, name, name_norm, kind, now_line, x, y, person_id, created_at,"
        " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (public_id, name, name_norm, kind, now_line, x, y, person_id, now, now),
    )
    hub = get(conn, int(cur.lastrowid or 0))
    assert hub is not None
    return hub


def get(conn: sqlite3.Connection, hub_id: int) -> Hub | None:
    return _hub(conn.execute("SELECT * FROM hubs WHERE id = ?", (hub_id,)).fetchone())


def by_public_id(conn: sqlite3.Connection, public_id: str) -> Hub | None:
    return _hub(conn.execute("SELECT * FROM hubs WHERE public_id = ?", (public_id,)).fetchone())


def by_name_norm(conn: sqlite3.Connection, name_norm: str) -> Hub | None:
    row = conn.execute(
        "SELECT * FROM hubs WHERE name_norm = ? AND archived = 0", (name_norm,)
    ).fetchone()
    return _hub(row)


def active(conn: sqlite3.Connection) -> list[Hub]:
    rows = conn.execute("SELECT * FROM hubs WHERE archived = 0 ORDER BY id").fetchall()
    return [h for h in map(_hub, rows) if h is not None]


def all_hubs(conn: sqlite3.Connection) -> list[Hub]:
    rows = conn.execute("SELECT * FROM hubs ORDER BY id").fetchall()
    return [h for h in map(_hub, rows) if h is not None]


def shelves(conn: sqlite3.Connection) -> list[Hub]:
    rows = conn.execute("SELECT * FROM hubs WHERE kind = 'shelf' ORDER BY id").fetchall()
    return [h for h in map(_hub, rows) if h is not None]


def by_person(conn: sqlite3.Connection, person_id: int) -> Hub | None:
    row = conn.execute(
        "SELECT * FROM hubs WHERE person_id = ? AND archived = 0", (person_id,)
    ).fetchone()
    return _hub(row)


def set_now_line(conn: sqlite3.Connection, hub_id: int, now_line: str, now: int) -> None:
    conn.execute(
        "UPDATE hubs SET now_line = ?, updated_at = ? WHERE id = ?", (now_line, now, hub_id)
    )


def rename(conn: sqlite3.Connection, hub_id: int, name: str, name_norm: str, now: int) -> None:
    conn.execute(
        "UPDATE hubs SET name = ?, name_norm = ?, updated_at = ? WHERE id = ?",
        (name, name_norm, now, hub_id),
    )


def set_archived(
    conn: sqlite3.Connection, hub_id: int, archived: bool, now: int, merged_into: int | None
) -> None:
    conn.execute(
        "UPDATE hubs SET archived = ?, merged_into = ?, updated_at = ? WHERE id = ?",
        (int(archived), merged_into, now, hub_id),
    )


def delete(conn: sqlite3.Connection, hub_id: int) -> None:
    conn.execute("DELETE FROM hubs WHERE id = ?", (hub_id,))


# Members -------------------------------------------------------------------------


def add_member(
    conn: sqlite3.Connection,
    *,
    hub_id: int,
    nugget_id: int,
    role: str,
    since: int,
    decided_by: str,
    is_primary: bool = False,
    confidence: float | None = None,
    evidence: str = "",
    until: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO hub_members(hub_id, nugget_id, role, is_primary, since, until, decided_by,"
        " confidence, evidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(hub_id, nugget_id) DO UPDATE SET role=excluded.role,"
        " is_primary=MAX(hub_members.is_primary, excluded.is_primary), until=excluded.until,"
        " decided_by=excluded.decided_by, confidence=excluded.confidence,"
        " evidence=CASE WHEN excluded.evidence <> '' THEN excluded.evidence"
        " ELSE hub_members.evidence END",
        (
            hub_id,
            nugget_id,
            role,
            int(is_primary),
            since,
            until,
            decided_by,
            confidence,
            evidence,
        ),
    )


def member(conn: sqlite3.Connection, hub_id: int, nugget_id: int) -> Member | None:
    row = conn.execute(
        "SELECT * FROM hub_members WHERE hub_id = ? AND nugget_id = ?", (hub_id, nugget_id)
    ).fetchone()
    return _member(row) if row else None


def set_role(
    conn: sqlite3.Connection,
    hub_id: int,
    nugget_id: int,
    role: str,
    until: int | None,
    decided_by: str,
) -> None:
    conn.execute(
        "UPDATE hub_members SET role = ?, until = ?, decided_by = ? WHERE hub_id = ?"
        " AND nugget_id = ?",
        (role, until, decided_by, hub_id, nugget_id),
    )


def remove_member(conn: sqlite3.Connection, hub_id: int, nugget_id: int) -> None:
    conn.execute("DELETE FROM hub_members WHERE hub_id = ? AND nugget_id = ?", (hub_id, nugget_id))


def set_primary(conn: sqlite3.Connection, nugget_id: int, hub_id: int) -> None:
    conn.execute("UPDATE hub_members SET is_primary = 0 WHERE nugget_id = ?", (nugget_id,))
    conn.execute(
        "UPDATE hub_members SET is_primary = 1 WHERE nugget_id = ? AND hub_id = ?",
        (nugget_id, hub_id),
    )


def memberships(conn: sqlite3.Connection, nugget_id: int) -> list[Member]:
    rows = conn.execute(
        "SELECT * FROM hub_members WHERE nugget_id = ? ORDER BY is_primary DESC, since",
        (nugget_id,),
    ).fetchall()
    return [_member(r) for r in rows]


def primary_hub(conn: sqlite3.Connection, nugget_id: int) -> Hub | None:
    row = conn.execute(
        "SELECT h.* FROM hubs h JOIN hub_members m ON m.hub_id = h.id WHERE m.nugget_id = ?"
        " AND m.is_primary = 1",
        (nugget_id,),
    ).fetchone()
    return _hub(row)


def members(
    conn: sqlite3.Connection, hub_id: int, roles: tuple[str, ...] | None = None
) -> list[Member]:
    if roles:
        marks = ",".join("?" * len(roles))
        rows = conn.execute(
            "SELECT m.* FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id WHERE m.hub_id = ?"
            f" AND m.role IN ({marks}) AND n.deleted_at IS NULL ORDER BY m.since",
            (hub_id, *roles),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT m.* FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id WHERE m.hub_id = ?"
            " AND n.deleted_at IS NULL ORDER BY m.since",
            (hub_id,),
        ).fetchall()
    return [_member(r) for r in rows]


def member_count(conn: sqlite3.Connection, hub_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id"
        " WHERE m.hub_id = ? AND n.deleted_at IS NULL",
        (hub_id,),
    ).fetchone()
    return int(row[0])


def counts(conn: sqlite3.Connection) -> dict[int, int]:
    rows = conn.execute(
        "SELECT m.hub_id, COUNT(*) FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id"
        " WHERE n.deleted_at IS NULL GROUP BY m.hub_id"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def primary_counts(conn: sqlite3.Connection) -> dict[int, int]:
    rows = conn.execute(
        "SELECT m.hub_id, COUNT(*) FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id"
        " WHERE n.deleted_at IS NULL AND m.is_primary = 1 GROUP BY m.hub_id"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def recent_member_titles(conn: sqlite3.Connection, hub_id: int, limit: int = 30) -> list[str]:
    rows = conn.execute(
        "SELECT e.title FROM hub_members m JOIN enrichments e ON e.nugget_id = m.nugget_id"
        " JOIN nuggets n ON n.id = m.nugget_id WHERE m.hub_id = ? AND n.deleted_at IS NULL"
        " ORDER BY n.captured_at DESC LIMIT ?",
        (hub_id, limit),
    ).fetchall()
    return [r[0] for r in rows]


def nuggets_without_hub(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT n.id FROM nuggets n WHERE n.status = 'filed' AND n.deleted_at IS NULL AND NOT"
        " EXISTS (SELECT 1 FROM hub_members m WHERE m.nugget_id = n.id)"
    ).fetchall()
    return [r[0] for r in rows]
