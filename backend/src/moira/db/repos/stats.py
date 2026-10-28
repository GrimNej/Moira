"""Counts for the daily digest (§13.15). Numbers only: never content."""

import sqlite3


def saves_between(conn: sqlite3.Connection, start: int, end: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM nuggets WHERE captured_at >= ? AND captured_at < ? AND is_sample = 0",
        (start, end),
    ).fetchone()
    return int(row[0])


def questions_between(conn: sqlite3.Connection, start: int, end: int) -> tuple[int, int, int]:
    """(questions, found it, not it)."""
    row = conn.execute(
        "SELECT COUNT(*), SUM(feedback = 'found'), SUM(feedback = 'not_it') FROM turns"
        " WHERE created_at >= ? AND created_at < ?",
        (start, end),
    ).fetchone()
    return int(row[0]), int(row[1] or 0), int(row[2] or 0)


def research_between(conn: sqlite3.Connection, start: int, end: int) -> dict[str, int]:
    """Web research outcomes: verified, possible, not found."""
    row = conn.execute(
        "SELECT SUM(status = 'ok' AND verified = 1), SUM(status = 'ok' AND verified = 0),"
        " SUM(status = 'not_found') FROM research"
        " WHERE method = 'web_search' AND created_at >= ? AND created_at < ?",
        (start, end),
    ).fetchone()
    return {
        "verified": int(row[0] or 0),
        "possible": int(row[1] or 0),
        "not_found": int(row[2] or 0),
    }


def ai_events_since(conn: sqlite3.Connection, since: int, prefix: str) -> list[sqlite3.Row]:
    """Event groups the AI made since ``since`` whose id starts with ``prefix`` (e.g. tidy)."""
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT group_id, event, before_json, after_json, undone FROM hub_events"
        " WHERE actor = 'ai' AND created_at >= ? AND group_id LIKE ? ORDER BY id",
        (since, prefix + ":%"),
    ).fetchall()
    return rows


def unmasked_secret_candidates(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Every live nugget's raw text, for the nightly secret audit (read in code, never logged)."""
    return [
        (int(r[0]), str(r[1]))
        for r in conn.execute("SELECT id, user_text FROM nuggets WHERE deleted_at IS NULL")
    ]
