"""FTS5 channels (§8.2). Every term is quoted, so FTS operators in a query are inert (N.5)."""

import re
import sqlite3

WORD = re.compile(r"[\w']+", re.UNICODE)
# bm25 column weights (§6.3): title, summary, user_text, content_text, questions, tags,
# research, hub_names.
BM25 = "bm25(nugget_fts, 6, 3, 4, 2, 3, 2, 1.5, 1)"


def quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def fts_query(terms: list[str], *, prefix_last: bool = True) -> str:
    """Quote every term, double inner quotes, prefix only the last term; OR them."""
    q = [quote(t) for t in terms if t.strip()]
    if q and prefix_last:
        q[-1] += "*"
    return " OR ".join(q)


def words(text: str) -> list[str]:
    return [w.strip("'").lower() for w in WORD.findall(text) if w.strip("'")]


def search(conn: sqlite3.Connection, terms: list[str], limit: int = 100) -> list[int]:
    """Live nugget ids ranked by bm25 (lower is better)."""
    q = fts_query(terms)
    if not q:
        return []
    rows = conn.execute(
        f"SELECT f.rowid FROM nugget_fts f JOIN nuggets n ON n.id = f.rowid"  # noqa: S608
        f" WHERE nugget_fts MATCH ? AND n.deleted_at IS NULL ORDER BY {BM25} LIMIT ?",
        (q, limit),
    ).fetchall()
    return [r[0] for r in rows]


def search_hubs(conn: sqlite3.Connection, terms: list[str], limit: int = 5) -> list[int]:
    q = fts_query(terms)
    if not q:
        return []
    rows = conn.execute(
        "SELECT f.rowid FROM hub_fts f JOIN hubs h ON h.id = f.rowid WHERE hub_fts MATCH ?"
        " AND h.archived = 0 ORDER BY bm25(hub_fts, 4, 2, 1) LIMIT ?",
        (q, limit),
    ).fetchall()
    return [r[0] for r in rows]


def match_ids(conn: sqlite3.Connection, terms: list[str]) -> str | None:
    """The MATCH expression for the deep tier's SQL filter, or None."""
    return fts_query(terms, prefix_last=False) or None
