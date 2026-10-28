"""Search index maintenance (§6.3): FTS, trigram and vectors, written by code (no triggers).

``index_instant`` runs at capture (raw text only); ``index_full`` after filing adds the
derived fields. Both are idempotent: delete then insert.
"""

import json
import sqlite3

from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.embed.model import Embedder
from moira.search import vectors


def _tri_text(conn: sqlite3.Connection, nugget_id: int) -> str:
    n = repo.get(conn, nugget_id)
    assert n is not None
    exacts = " ".join(r["value"] for r in repo.exacts_for(conn, nugget_id))
    return "\n".join(p for p in (n.user_text, n.content_text, exacts, n.url or "") if p)


def link_title(conn: sqlite3.Connection, nugget_id: int) -> str:
    for r in repo.research_for(conn, nugget_id):
        if r["status"] == "ok" and r["title"]:
            return str(r["title"])
    return ""


def _replace_fts(conn: sqlite3.Connection, nugget_id: int, cols: dict[str, str]) -> None:
    conn.execute("DELETE FROM nugget_fts WHERE rowid = ?", (nugget_id,))
    conn.execute(
        "INSERT INTO nugget_fts(rowid, title, summary, user_text, content_text, questions, tags,"
        " research, hub_names) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            nugget_id,
            cols.get("title", ""),
            cols.get("summary", ""),
            cols.get("user_text", ""),
            cols.get("content_text", ""),
            cols.get("questions", ""),
            cols.get("tags", ""),
            cols.get("research", ""),
            cols.get("hub_names", ""),
        ),
    )


def _replace_tri(conn: sqlite3.Connection, nugget_id: int) -> None:
    conn.execute("DELETE FROM nugget_tri WHERE rowid = ?", (nugget_id,))
    conn.execute(
        "INSERT INTO nugget_tri(rowid, text) VALUES (?, ?)", (nugget_id, _tri_text(conn, nugget_id))
    )


def index_instant(conn: sqlite3.Connection, nugget_id: int, embedder: Embedder | None) -> None:
    """Trigram + FTS(user_text, content_text) + vector(user_text + link title)."""
    n = repo.get(conn, nugget_id)
    assert n is not None
    _replace_tri(conn, nugget_id)
    _replace_fts(conn, nugget_id, {"user_text": n.user_text, "content_text": n.content_text})
    if embedder is not None:
        text = " ".join(p for p in (n.user_text, link_title(conn, nugget_id)) if p) or n.url or ""
        if text:
            vectors.upsert(conn, "vec_nuggets", nugget_id, embedder.encode([text])[0])


def embed_text(conn: sqlite3.Connection, nugget_id: int) -> str:
    """§7.6: title + summary + tags + questions + user_text[:500] + link title."""
    n = repo.get(conn, nugget_id)
    e = repo.enrichment(conn, nugget_id)
    assert n is not None
    parts: list[str] = []
    if e is not None:
        parts += [e["title"], e["summary"], " ".join(json.loads(e["tags"]))]
        parts += json.loads(e["questions"])
    parts += [n.user_text[:500], link_title(conn, nugget_id)]
    return " ".join(p for p in parts if p)


def index_full(conn: sqlite3.Connection, nugget_id: int, embedder: Embedder | None) -> None:
    """All FTS columns, trigram and the full vector, after filing or a refresh."""
    n = repo.get(conn, nugget_id)
    assert n is not None
    e = repo.enrichment(conn, nugget_id)
    research = " ".join(
        f"{r['title']} {r['author']} {r['findings']}" for r in repo.research_for(conn, nugget_id)
    )
    hub_names = " ".join(
        h.name
        for m in hubs_repo.memberships(conn, nugget_id)
        if (h := hubs_repo.get(conn, m.hub_id)) is not None
    )
    cols = {
        "user_text": n.user_text,
        "content_text": n.content_text,
        "research": research,
        "hub_names": hub_names,
    }
    if e is not None:
        cols.update(
            title=e["title"],
            summary=e["summary"],
            questions=" ".join(json.loads(e["questions"])),
            tags=" ".join(json.loads(e["tags"])),
        )
    _replace_fts(conn, nugget_id, cols)
    _replace_tri(conn, nugget_id)
    if embedder is not None:
        vectors.upsert(
            conn, "vec_nuggets", nugget_id, embedder.encode([embed_text(conn, nugget_id)])[0]
        )


def unindex(conn: sqlite3.Connection, nugget_id: int) -> None:
    conn.execute("DELETE FROM nugget_fts WHERE rowid = ?", (nugget_id,))
    conn.execute("DELETE FROM nugget_tri WHERE rowid = ?", (nugget_id,))
    vectors.delete(conn, "vec_nuggets", nugget_id)


def index_hub(conn: sqlite3.Connection, hub_id: int, embedder: Embedder | None) -> None:
    """hub_fts row and the hub vector (§7.6: mean of recent members + 0.5 × name vector)."""
    hub = hubs_repo.get(conn, hub_id)
    assert hub is not None
    titles = hubs_repo.recent_member_titles(conn, hub_id, 30)
    conn.execute("DELETE FROM hub_fts WHERE rowid = ?", (hub_id,))
    conn.execute(
        "INSERT INTO hub_fts(rowid, name, now_line, member_titles) VALUES (?, ?, ?, ?)",
        (hub_id, hub.name, hub.now_line, " ".join(titles)),
    )
    if embedder is None:
        return
    import numpy as np

    member_ids = [m.nugget_id for m in hubs_repo.members(conn, hub_id)][-200:]
    vecs = list(vectors.many(conn, "vec_nuggets", member_ids).values())
    name_vec = embedder.encode([hub.name])[0]
    combined = (np.mean(vecs, axis=0) if vecs else np.zeros_like(name_vec)) + 0.5 * name_vec
    norm = float(np.linalg.norm(combined)) or 1.0
    vectors.upsert(conn, "vec_hubs", hub_id, (combined / norm).astype(np.float32))


def consistency_repair(conn: sqlite3.Connection, embedder: Embedder | None) -> int:
    """Invariant 7: every live nugget has FTS, trigram and vector rows (nightly)."""
    live = set(repo.all_live_ids(conn))
    have_fts = {r[0] for r in conn.execute("SELECT rowid FROM nugget_fts")}
    have_tri = {r[0] for r in conn.execute("SELECT rowid FROM nugget_tri")}
    have_vec = {r[0] for r in conn.execute("SELECT rowid FROM vec_nuggets")}
    repaired = 0
    for nid in live:
        if nid not in have_fts or nid not in have_tri or (embedder and nid not in have_vec):
            index_full(conn, nid, embedder)
            repaired += 1
    for stale in (have_fts | have_tri) - live:
        unindex(conn, stale)
    return repaired
