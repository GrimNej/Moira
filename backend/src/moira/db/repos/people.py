"""People with aliases and disambiguators (§6.3, §7.8)."""

import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Person:
    id: int
    public_id: str
    display_name: str
    aliases: list[str]
    disambiguator: str
    created_at: int


def _person(row: sqlite3.Row | None) -> Person | None:
    if row is None:
        return None
    return Person(
        id=row["id"],
        public_id=row["public_id"],
        display_name=row["display_name"],
        aliases=json.loads(row["aliases"]),
        disambiguator=row["disambiguator"],
        created_at=row["created_at"],
    )


def create(
    conn: sqlite3.Connection,
    *,
    public_id: str,
    display_name: str,
    now: int,
    aliases: list[str] | None = None,
    disambiguator: str = "",
) -> Person:
    cur = conn.execute(
        "INSERT INTO people(public_id, display_name, aliases, disambiguator, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (public_id, display_name, json.dumps(aliases or []), disambiguator, now),
    )
    p = get(conn, int(cur.lastrowid or 0))
    assert p is not None
    return p


def get(conn: sqlite3.Connection, person_id: int) -> Person | None:
    return _person(conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone())


def all_people(conn: sqlite3.Connection) -> list[Person]:
    rows = conn.execute("SELECT * FROM people ORDER BY id").fetchall()
    return [p for p in map(_person, rows) if p is not None]


def update(
    conn: sqlite3.Connection, person_id: int, *, aliases: list[str], disambiguator: str
) -> None:
    conn.execute(
        "UPDATE people SET aliases = ?, disambiguator = ? WHERE id = ?",
        (json.dumps(aliases), disambiguator, person_id),
    )


def link_nugget(conn: sqlite3.Connection, nugget_id: int, person_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO nugget_people(nugget_id, person_id) VALUES (?, ?)",
        (nugget_id, person_id),
    )


def for_nugget(conn: sqlite3.Connection, nugget_id: int) -> list[Person]:
    rows = conn.execute(
        "SELECT p.* FROM people p JOIN nugget_people np ON np.person_id = p.id"
        " WHERE np.nugget_id = ?",
        (nugget_id,),
    ).fetchall()
    return [p for p in map(_person, rows) if p is not None]


def nuggets_of(conn: sqlite3.Connection, person_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT np.nugget_id FROM nugget_people np JOIN nuggets n ON n.id = np.nugget_id"
        " WHERE np.person_id = ? AND n.deleted_at IS NULL",
        (person_id,),
    )
    return [r[0] for r in rows]
