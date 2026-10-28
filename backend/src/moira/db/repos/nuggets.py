"""Nuggets and their raw layer: raw events, versions, exacts, enrichments, research (§6.3).

The raw layer (``user_text``) changes only through ``add_version`` (invariant 4).
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Nugget:
    id: int
    public_id: str
    source: str
    user_text: str
    content_text: str
    url: str | None
    url_canonical: str | None
    captured_at: int
    captured_tz: str
    original_posted_at: int | None
    forward_from: str | None
    status: str
    version: int
    dedupe_key: str | None
    saved_count: int
    open_count: int
    pinned: bool
    has_masked_secret: bool
    is_sample: bool
    deleted_at: int | None
    created_at: int
    updated_at: int


def _nugget(row: sqlite3.Row | None) -> Nugget | None:
    if row is None:
        return None
    return Nugget(
        id=row["id"],
        public_id=row["public_id"],
        source=row["source"],
        user_text=row["user_text"],
        content_text=row["content_text"],
        url=row["url"],
        url_canonical=row["url_canonical"],
        captured_at=row["captured_at"],
        captured_tz=row["captured_tz"],
        original_posted_at=row["original_posted_at"],
        forward_from=row["forward_from"],
        status=row["status"],
        version=row["version"],
        dedupe_key=row["dedupe_key"],
        saved_count=row["saved_count"],
        open_count=row["open_count"],
        pinned=bool(row["pinned"]),
        has_masked_secret=bool(row["has_masked_secret"]),
        is_sample=bool(row["is_sample"]),
        deleted_at=row["deleted_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def insert(
    conn: sqlite3.Connection,
    *,
    public_id: str,
    source: str,
    user_text: str,
    captured_at: int,
    captured_tz: str,
    now: int,
    url: str | None = None,
    url_canonical: str | None = None,
    original_posted_at: int | None = None,
    forward_from: str | None = None,
    dedupe_key: str | None = None,
    has_masked_secret: bool = False,
    is_sample: bool = False,
    content_text: str = "",
) -> Nugget:
    cur = conn.execute(
        "INSERT INTO nuggets(public_id, source, user_text, content_text, url, url_canonical,"
        " captured_at, captured_tz, original_posted_at, forward_from, dedupe_key,"
        " has_masked_secret, is_sample, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            public_id,
            source,
            user_text,
            content_text,
            url,
            url_canonical,
            captured_at,
            captured_tz,
            original_posted_at,
            forward_from,
            dedupe_key,
            int(has_masked_secret),
            int(is_sample),
            now,
            now,
        ),
    )
    n = get(conn, int(cur.lastrowid or 0))
    assert n is not None
    return n


def get(conn: sqlite3.Connection, nugget_id: int) -> Nugget | None:
    return _nugget(conn.execute("SELECT * FROM nuggets WHERE id = ?", (nugget_id,)).fetchone())


def by_public_id(conn: sqlite3.Connection, public_id: str) -> Nugget | None:
    row = conn.execute("SELECT * FROM nuggets WHERE public_id = ?", (public_id,)).fetchone()
    return _nugget(row)


def many(conn: sqlite3.Connection, ids: list[int]) -> list[Nugget]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM nuggets WHERE id IN ({marks}) AND deleted_at IS NULL",
        ids,
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    return [n for n in (_nugget(by_id.get(i)) for i in ids) if n is not None]


def find_by_dedupe(conn: sqlite3.Connection, key: str) -> Nugget | None:
    row = conn.execute(
        "SELECT * FROM nuggets WHERE dedupe_key = ? AND deleted_at IS NULL"
        " ORDER BY captured_at DESC LIMIT 1",
        (key,),
    ).fetchone()
    return _nugget(row)


def bump_saved_count(conn: sqlite3.Connection, nugget_id: int, now: int) -> None:
    conn.execute(
        "UPDATE nuggets SET saved_count = saved_count + 1, updated_at = ? WHERE id = ?",
        (now, nugget_id),
    )


def bump_open_count(conn: sqlite3.Connection, nugget_id: int) -> None:
    conn.execute("UPDATE nuggets SET open_count = open_count + 1 WHERE id = ?", (nugget_id,))


def set_status(conn: sqlite3.Connection, nugget_id: int, status: str, now: int) -> None:
    conn.execute(
        "UPDATE nuggets SET status = ?, updated_at = ? WHERE id = ?", (status, now, nugget_id)
    )


def append_user_text(conn: sqlite3.Connection, nugget_id: int, text: str, now: int) -> None:
    """Join another part of the same capture group (§7.1.1). Not an edit: no version."""
    conn.execute(
        "UPDATE nuggets SET user_text = CASE WHEN user_text = '' THEN ? ELSE user_text || char(10)"
        " || ? END, updated_at = ? WHERE id = ?",
        (text, text, now, nugget_id),
    )


def set_url(
    conn: sqlite3.Connection, nugget_id: int, url: str, canonical: str, source: str, now: int
) -> None:
    conn.execute(
        "UPDATE nuggets SET url = COALESCE(url, ?), url_canonical = COALESCE(url_canonical, ?),"
        " dedupe_key = COALESCE(url_canonical, ?), source = CASE WHEN source IN"
        " ('typed','forward') THEN ? ELSE source END, updated_at = ? WHERE id = ?",
        (url, canonical, canonical, source, now, nugget_id),
    )


def set_source(conn: sqlite3.Connection, nugget_id: int, source: str, now: int) -> None:
    conn.execute(
        "UPDATE nuggets SET source = ?, updated_at = ? WHERE id = ?", (source, now, nugget_id)
    )


def append_content_text(conn: sqlite3.Connection, nugget_id: int, text: str, now: int) -> None:
    conn.execute(
        "UPDATE nuggets SET content_text = CASE WHEN content_text = '' THEN ? ELSE content_text"
        " || char(10) || ? END, updated_at = ? WHERE id = ?",
        (text, text, now, nugget_id),
    )


def set_user_text_from_media(
    conn: sqlite3.Connection, nugget_id: int, text: str, has_secret: bool, now: int
) -> None:
    """A voice transcript *is* the user's words (§7.2.1): appended to the raw text."""
    append_user_text(conn, nugget_id, text, now)
    if has_secret:
        conn.execute("UPDATE nuggets SET has_masked_secret = 1 WHERE id = ?", (nugget_id,))


def add_version(
    conn: sqlite3.Connection, nugget_id: int, user_text: str, edited_via: str, now: int
) -> int:
    """A user edit: keep the old text as a version, then change the raw text (invariant 4)."""
    n = get(conn, nugget_id)
    assert n is not None
    conn.execute(
        "INSERT INTO nugget_versions(nugget_id, version, user_text, edited_at, edited_via)"
        " VALUES (?, ?, ?, ?, ?)",
        (nugget_id, n.version, n.user_text, now, edited_via),
    )
    conn.execute(
        "UPDATE nuggets SET user_text = ?, version = version + 1, updated_at = ? WHERE id = ?",
        (user_text, now, nugget_id),
    )
    return n.version + 1


def versions(conn: sqlite3.Connection, nugget_id: int) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM nugget_versions WHERE nugget_id = ? ORDER BY version", (nugget_id,)
    ).fetchall()
    return rows


def soft_delete(conn: sqlite3.Connection, nugget_id: int, now: int) -> None:
    conn.execute(
        "UPDATE nuggets SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, nugget_id)
    )


def restore_deleted(conn: sqlite3.Connection, nugget_id: int, now: int) -> None:
    conn.execute(
        "UPDATE nuggets SET deleted_at = NULL, updated_at = ? WHERE id = ?", (now, nugget_id)
    )


def hard_delete(conn: sqlite3.Connection, nugget_id: int) -> None:
    conn.execute("DELETE FROM nuggets WHERE id = ?", (nugget_id,))


def recent(
    conn: sqlite3.Connection,
    *,
    limit: int,
    before: tuple[int, int] | None = None,
    sources: tuple[str, ...] | None = None,
    kinds: tuple[str, ...] | None = None,
    hub_id: int | None = None,
) -> list[Nugget]:
    sql = ["SELECT n.* FROM nuggets n LEFT JOIN enrichments e ON e.nugget_id = n.id"]
    where = ["n.deleted_at IS NULL"]
    args: list[Any] = []
    if hub_id is not None:
        sql.append("JOIN hub_members m ON m.nugget_id = n.id AND m.hub_id = ?")
        args.append(hub_id)
    if before is not None:
        where.append("(n.captured_at < ? OR (n.captured_at = ? AND n.id < ?))")
        args += [before[0], before[0], before[1]]
    if sources:
        where.append(f"n.source IN ({','.join('?' * len(sources))})")
        args += list(sources)
    if kinds:
        where.append(f"e.kind IN ({','.join('?' * len(kinds))})")
        args += list(kinds)
    sql.append("WHERE " + " AND ".join(where))
    sql.append("ORDER BY n.captured_at DESC, n.id DESC LIMIT ?")
    args.append(limit)
    rows = conn.execute(" ".join(sql), args).fetchall()
    return [n for n in map(_nugget, rows) if n is not None]


def all_live_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM nuggets WHERE deleted_at IS NULL")]


def deleted_before(conn: sqlite3.Connection, when: int) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM nuggets WHERE deleted_at IS NOT NULL AND deleted_at <= ?", (when,)
    )
    return [r[0] for r in rows]


def previous(conn: sqlite3.Connection, n: Nugget) -> Nugget | None:
    row = conn.execute(
        "SELECT * FROM nuggets WHERE deleted_at IS NULL AND (captured_at < ? OR (captured_at = ?"
        " AND id < ?)) ORDER BY captured_at DESC, id DESC LIMIT 1",
        (n.captured_at, n.captured_at, n.id),
    ).fetchone()
    return _nugget(row)


def count_live(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM nuggets WHERE deleted_at IS NULL").fetchone()[0])


def first_captured_at(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MIN(captured_at) FROM nuggets WHERE deleted_at IS NULL").fetchone()
    return int(row[0]) if row[0] is not None else None


# Raw events ----------------------------------------------------------------------


def insert_raw_event(
    conn: sqlite3.Connection,
    *,
    channel: str,
    kind: str,
    text: str | None,
    received_at: int,
    external_id: str | None = None,
    media_meta: dict[str, Any] | None = None,
    original_posted_at: int | None = None,
    edit_of: int | None = None,
    nugget_id: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO raw_events(channel, external_id, kind, text, media_meta, received_at,"
        " original_posted_at, edit_of, nugget_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            channel,
            external_id,
            kind,
            text,
            json.dumps(media_meta) if media_meta else None,
            received_at,
            original_posted_at,
            edit_of,
            nugget_id,
        ),
    )
    return int(cur.lastrowid or 0)


def raw_event_by_external(
    conn: sqlite3.Connection, channel: str, external_id: str
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM raw_events WHERE channel = ? AND external_id = ? AND edit_of IS NULL",
        (channel, external_id),
    ).fetchone()
    return row


def raw_event(conn: sqlite3.Connection, raw_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM raw_events WHERE id = ?", (raw_id,)
    ).fetchone()
    return row


def link_raw_event(conn: sqlite3.Connection, raw_id: int, nugget_id: int) -> None:
    conn.execute("UPDATE raw_events SET nugget_id = ? WHERE id = ?", (nugget_id, raw_id))


def raw_events_for(conn: sqlite3.Connection, nugget_id: int) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM raw_events WHERE nugget_id = ? ORDER BY id", (nugget_id,)
    ).fetchall()
    return rows


# Exacts --------------------------------------------------------------------------


def insert_exacts(
    conn: sqlite3.Connection, nugget_id: int, items: list[tuple[str, str, str]], origin: str
) -> None:
    """``items`` are (kind, value, normalized)."""
    conn.executemany(
        "INSERT INTO exacts(nugget_id, kind, value, normalized, origin) VALUES (?, ?, ?, ?, ?)",
        [(nugget_id, k, v, n, origin) for k, v, n in items],
    )


def exacts_for(conn: sqlite3.Connection, nugget_id: int) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM exacts WHERE nugget_id = ? ORDER BY id", (nugget_id,)
    ).fetchall()
    return rows


def delete_exacts(conn: sqlite3.Connection, nugget_id: int, origin: str | None = None) -> None:
    if origin is None:
        conn.execute("DELETE FROM exacts WHERE nugget_id = ?", (nugget_id,))
    else:
        conn.execute("DELETE FROM exacts WHERE nugget_id = ? AND origin = ?", (nugget_id, origin))


def find_exact(conn: sqlite3.Connection, kind: str | None, normalized: str) -> list[int]:
    if kind is None:
        rows = conn.execute(
            "SELECT DISTINCT e.nugget_id FROM exacts e JOIN nuggets n ON n.id = e.nugget_id"
            " WHERE e.normalized = ? AND n.deleted_at IS NULL",
            (normalized,),
        )
    else:
        rows = conn.execute(
            "SELECT DISTINCT e.nugget_id FROM exacts e JOIN nuggets n ON n.id = e.nugget_id"
            " WHERE e.kind = ? AND e.normalized = ? AND n.deleted_at IS NULL",
            (kind, normalized),
        )
    return [r[0] for r in rows]


def find_exact_prefix(conn: sqlite3.Connection, prefix: str, limit: int = 50) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT e.nugget_id FROM exacts e JOIN nuggets n ON n.id = e.nugget_id"
        " WHERE e.normalized >= ? AND e.normalized < ? AND n.deleted_at IS NULL LIMIT ?",
        (prefix, prefix + "￿", limit),
    )
    return [r[0] for r in rows]


# Enrichments ---------------------------------------------------------------------


def upsert_enrichment(
    conn: sqlite3.Connection,
    nugget_id: int,
    *,
    title: str,
    summary: str,
    kind: str,
    tags: list[str],
    questions: list[str],
    structured_list: dict[str, Any] | None,
    guess: str,
    model: str,
    prompt_version: str,
    raw_output: str,
    now: int,
) -> None:
    conn.execute(
        "INSERT INTO enrichments(nugget_id, title, summary, kind, tags, questions,"
        " structured_list, guess, model, prompt_version, raw_output, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(nugget_id) DO UPDATE SET"
        " title=excluded.title, summary=excluded.summary, kind=excluded.kind,"
        " tags=excluded.tags, questions=excluded.questions,"
        " structured_list=excluded.structured_list, guess=excluded.guess, model=excluded.model,"
        " prompt_version=excluded.prompt_version, raw_output=excluded.raw_output,"
        " updated_at=excluded.updated_at",
        (
            nugget_id,
            title,
            summary,
            kind,
            json.dumps(tags),
            json.dumps(questions),
            json.dumps(structured_list) if structured_list else None,
            guess,
            model,
            prompt_version,
            raw_output,
            now,
            now,
        ),
    )


def enrichment(conn: sqlite3.Connection, nugget_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM enrichments WHERE nugget_id = ?", (nugget_id,)
    ).fetchone()
    return row


def enrichments_for(conn: sqlite3.Connection, ids: list[int]) -> dict[int, sqlite3.Row]:
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM enrichments WHERE nugget_id IN ({marks})",
        ids,
    ).fetchall()
    return {r["nugget_id"]: r for r in rows}


# Research ------------------------------------------------------------------------


def insert_research(
    conn: sqlite3.Connection,
    nugget_id: int,
    *,
    method: str,
    status: str,
    now: int,
    title: str = "",
    author: str = "",
    findings: str = "",
    excerpt: str = "",
    sources: list[dict[str, str]] | None = None,
    verified: bool | None = None,
    searches: int = 0,
    attempt: int = 1,
    next_retry_at: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO research(nugget_id, method, status, title, author, findings, excerpt,"
        " sources, verified, searches, attempt, next_retry_at, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            nugget_id,
            method,
            status,
            title,
            author,
            findings,
            excerpt[:3000],
            json.dumps(sources or []),
            None if verified is None else int(verified),
            searches,
            attempt,
            next_retry_at,
            now,
        ),
    )
    return int(cur.lastrowid or 0)


def research_for(conn: sqlite3.Connection, nugget_id: int) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM research WHERE nugget_id = ? ORDER BY id", (nugget_id,)
    ).fetchall()
    return rows


def research_by_canonical(conn: sqlite3.Connection, canonical: str) -> list[sqlite3.Row]:
    """Readings of the same canonical URL, to reuse instead of fetching again (§7.3.2)."""
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT r.* FROM research r JOIN nuggets n ON n.id = r.nugget_id WHERE n.url_canonical = ?"
        " AND r.status = 'ok' AND r.method IN ('youtube_oembed','github_api','page_fetch')"
        " ORDER BY r.id DESC",
        (canonical,),
    ).fetchall()
    return rows
