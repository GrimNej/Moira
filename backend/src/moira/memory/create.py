"""Create a new memory database: schema, meta and the 10 shelves on the ring (§6.3, §7.7.1)."""

import sqlite3
from pathlib import Path
from typing import Literal

from moira import ids
from moira.db.connection import open_db
from moira.db.migrate import migrate
from moira.db.repos import hubs
from moira.domain.shelves import SHELVES, shelf_position
from moira.domain.text import name_norm

MemoryKind = Literal["user", "sandbox", "template"]


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = "
        "excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def create_memory(
    path: Path | str,
    *,
    kind: MemoryKind,
    now: int,
    embed_model: str = "minishlab/potion-retrieval-32M",
    embed_dim: int = 256,
) -> sqlite3.Connection:
    """Create (or open, if it already exists) a memory and return an open connection."""
    conn = open_db(path)
    migrate(conn, "memory", embed_dim=embed_dim)
    if get_meta(conn, "created_at") is None:
        conn.execute("BEGIN IMMEDIATE")
        for key, value in (
            ("created_at", str(now)),
            ("kind", kind),
            ("embed_model", embed_model),
            ("embed_dim", str(embed_dim)),
            ("layout_version", "1"),
        ):
            set_meta(conn, key, value)
        for i, name in enumerate(SHELVES):
            x, y = shelf_position(i)
            hubs.create(
                conn,
                public_id=ids.new("h_"),
                name=name,
                name_norm=name_norm(name),
                kind="shelf",
                x=x,
                y=y,
                now=now,
            )
        conn.execute("COMMIT")
    return conn
