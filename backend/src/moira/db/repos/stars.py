"""Stable star positions (§6.3, invariant 6: x/y never change after insert)."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Star:
    nugget_id: int
    x: float
    y: float
    importance: float
    placed_at: int
    layout_version: int


def _star(row: sqlite3.Row | None) -> Star | None:
    if row is None:
        return None
    return Star(
        nugget_id=row["nugget_id"],
        x=row["x"],
        y=row["y"],
        importance=row["importance"],
        placed_at=row["placed_at"],
        layout_version=row["layout_version"],
    )


def insert(
    conn: sqlite3.Connection, nugget_id: int, x: float, y: float, now: int, importance: float = 0.5
) -> None:
    """Insert once. A second call for the same nugget is ignored: positions never move."""
    conn.execute(
        "INSERT OR IGNORE INTO stars(nugget_id, x, y, importance, placed_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (nugget_id, x, y, importance, now),
    )


def get(conn: sqlite3.Connection, nugget_id: int) -> Star | None:
    return _star(conn.execute("SELECT * FROM stars WHERE nugget_id = ?", (nugget_id,)).fetchone())


def all_live(conn: sqlite3.Connection) -> list[Star]:
    rows = conn.execute(
        "SELECT s.* FROM stars s JOIN nuggets n ON n.id = s.nugget_id WHERE n.deleted_at IS NULL"
    ).fetchall()
    return [s for s in map(_star, rows) if s is not None]


def set_importance(conn: sqlite3.Connection, values: list[tuple[float, int]]) -> None:
    conn.executemany("UPDATE stars SET importance = ? WHERE nugget_id = ?", values)


def in_box(
    conn: sqlite3.Connection, x0: float, y0: float, x1: float, y1: float
) -> list[tuple[int, float, float]]:
    rows = conn.execute(
        "SELECT nugget_id, x, y FROM stars WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ?",
        (x0, x1, y0, y1),
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]
