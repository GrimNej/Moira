"""Hub and people channels (§8.2)."""

import sqlite3

import numpy as np
import numpy.typing as npt

from moira.db.repos import people as people_repo
from moira.search import fts, vectors


def hub_channel(
    conn: sqlite3.Connection, terms: list[str], query_vec: npt.NDArray[np.float32] | None
) -> list[int]:
    """Top 5 hubs (hub_fts + vec_hubs) → their current/member nuggets by importance (≤ 30 each)."""
    hub_ids: list[int] = list(fts.search_hubs(conn, terms, 5))
    if query_vec is not None:
        for hid, sim in vectors.knn(conn, "vec_hubs", query_vec, 5):
            if sim > 0.2 and hid not in hub_ids:
                hub_ids.append(hid)
    out: list[int] = []
    for hid in hub_ids[:5]:
        rows = conn.execute(
            "SELECT m.nugget_id FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id"
            " LEFT JOIN stars s ON s.nugget_id = m.nugget_id"
            " WHERE m.hub_id = ? AND m.role IN ('current','member') AND n.deleted_at IS NULL"
            " ORDER BY COALESCE(s.importance, 0.5) DESC LIMIT 30",
            (hid,),
        ).fetchall()
        for (nid,) in rows:
            if nid not in out:
                out.append(nid)
    return out[:100]


def people_channel(conn: sqlite3.Connection, text: str) -> list[int]:
    """Names or aliases in the question → their nuggets (newest first)."""
    words = {w.lower().removesuffix("'s") for w in text.replace("’", "'").split()}
    out: list[int] = []
    for p in people_repo.all_people(conn):
        names = {n.lower() for n in [p.display_name, *p.aliases] if n}
        names |= {n.split()[0] for n in names if n}
        if names & words:
            for nid in people_repo.nuggets_of(conn, p.id):
                if nid not in out:
                    out.append(nid)
    return out[:50]
