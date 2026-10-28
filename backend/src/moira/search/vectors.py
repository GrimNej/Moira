"""Vector storage and KNN on sqlite-vec, or a numpy brute-force fallback (§6.1, §7.6)."""

import sqlite3

import numpy as np
import numpy.typing as npt

from moira.db.connection import vec_available

Table = str  # "vec_nuggets" | "vec_hubs"
TABLES = ("vec_nuggets", "vec_hubs")


def _check(table: Table) -> None:
    if table not in TABLES:
        raise ValueError(table)


def upsert(
    conn: sqlite3.Connection, table: Table, rowid: int, vec: npt.NDArray[np.float32]
) -> None:
    """One vector per row; replace = delete + insert (N.5)."""
    _check(table)
    blob = np.asarray(vec, dtype=np.float32).tobytes()
    conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))  # noqa: S608
    conn.execute(f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)", (rowid, blob))  # noqa: S608


def delete(conn: sqlite3.Connection, table: Table, rowid: int) -> None:
    _check(table)
    conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))  # noqa: S608


def get(conn: sqlite3.Connection, table: Table, rowid: int) -> npt.NDArray[np.float32] | None:
    _check(table)
    row = conn.execute(f"SELECT embedding FROM {table} WHERE rowid = ?", (rowid,)).fetchone()  # noqa: S608
    return np.frombuffer(row[0], dtype=np.float32).copy() if row else None


def knn(
    conn: sqlite3.Connection, table: Table, query: npt.NDArray[np.float32], k: int
) -> list[tuple[int, float]]:
    """(rowid, cosine similarity) best first. Vectors are L2-normalized."""
    _check(table)
    q = np.asarray(query, dtype=np.float32)
    if vec_available():
        rows = conn.execute(
            f"SELECT rowid, distance FROM {table} WHERE embedding MATCH ? AND k = ?"  # noqa: S608
            " ORDER BY distance",
            (q.tobytes(), k),
        ).fetchall()
        # L2 distance d between unit vectors: cos = 1 − d²/2.
        return [(int(r[0]), float(1 - r[1] ** 2 / 2)) for r in rows]
    rows = conn.execute(f"SELECT rowid, embedding FROM {table}").fetchall()  # noqa: S608
    if not rows:
        return []
    ids = np.array([r[0] for r in rows])
    m = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    sims = m @ q
    order = np.argsort(-sims)[:k]
    return [(int(ids[i]), float(sims[i])) for i in order]


def many(
    conn: sqlite3.Connection, table: Table, rowids: list[int]
) -> dict[int, npt.NDArray[np.float32]]:
    _check(table)
    if not rowids:
        return {}
    marks = ",".join("?" * len(rowids))
    rows = conn.execute(
        f"SELECT rowid, embedding FROM {table} WHERE rowid IN ({marks})",  # noqa: S608
        rowids,
    ).fetchall()
    return {int(r[0]): np.frombuffer(r[1], dtype=np.float32).copy() for r in rows}
