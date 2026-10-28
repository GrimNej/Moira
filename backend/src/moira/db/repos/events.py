"""Hub events (history and undo) and conversation turns (§6.3)."""

import json
import sqlite3
from typing import Any


def record(
    conn: sqlite3.Connection,
    *,
    group_id: str,
    event: str,
    actor: str,
    now: int,
    hub_id: int | None = None,
    nugget_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO hub_events(group_id, hub_id, nugget_id, event, before_json, after_json, actor,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            group_id,
            hub_id,
            nugget_id,
            event,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            actor,
            now,
        ),
    )
    return int(cur.lastrowid or 0)


def group(conn: sqlite3.Connection, group_id: str) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM hub_events WHERE group_id = ? ORDER BY id", (group_id,)
    ).fetchall()
    return rows


def latest_undoable_group(conn: sqlite3.Connection, actors: tuple[str, ...]) -> str | None:
    marks = ",".join("?" * len(actors))
    row = conn.execute(
        f"SELECT group_id FROM hub_events WHERE undone = 0 AND event <> 'undone'"
        f" AND actor IN ({marks}) ORDER BY id DESC LIMIT 1",
        actors,
    ).fetchone()
    return str(row[0]) if row else None


def mark_undone(conn: sqlite3.Connection, group_id: str) -> None:
    conn.execute("UPDATE hub_events SET undone = 1 WHERE group_id = ?", (group_id,))


def for_hub(conn: sqlite3.Connection, hub_id: int, limit: int = 50) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM hub_events WHERE hub_id = ? ORDER BY id DESC LIMIT ?", (hub_id, limit)
    ).fetchall()
    return rows


def since(conn: sqlite3.Connection, when: int, actor: str) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM hub_events WHERE created_at >= ? AND actor = ? ORDER BY id", (when, actor)
    ).fetchall()
    return rows


# Conversations and turns ---------------------------------------------------------


def conversation(conn: sqlite3.Connection, public_id: str, now: int) -> int:
    row = conn.execute("SELECT id FROM conversations WHERE public_id = ?", (public_id,)).fetchone()
    if row:
        return int(row[0])
    cur = conn.execute(
        "INSERT INTO conversations(public_id, created_at) VALUES (?, ?)", (public_id, now)
    )
    return int(cur.lastrowid or 0)


def add_turn(
    conn: sqlite3.Connection,
    *,
    conversation_id: int,
    question: str,
    parsed: dict[str, Any],
    answer: str,
    cited: list[str],
    confidence: str,
    tier: str,
    latency_ms: int,
    est_usd: float,
    now: int,
) -> int:
    cur = conn.execute(
        "INSERT INTO turns(conversation_id, question, parsed, answer, cited, confidence, tier,"
        " latency_ms, est_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            conversation_id,
            question,
            json.dumps(parsed),
            answer,
            json.dumps(cited),
            confidence,
            tier,
            latency_ms,
            est_usd,
            now,
        ),
    )
    return int(cur.lastrowid or 0)


def last_turns(conn: sqlite3.Connection, conversation_id: int, n: int = 3) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT * FROM turns WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
        (conversation_id, n),
    ).fetchall()
    return list(reversed(rows))


def turn(conn: sqlite3.Connection, turn_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM turns WHERE id = ?", (turn_id,)
    ).fetchone()
    return row


def set_feedback(conn: sqlite3.Connection, turn_id: int, value: str) -> None:
    conn.execute("UPDATE turns SET feedback = ? WHERE id = ?", (value, turn_id))


def feedback_counts(conn: sqlite3.Connection, since_ms: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT feedback, COUNT(*) FROM turns WHERE created_at >= ? AND feedback IS NOT NULL"
        " GROUP BY feedback",
        (since_ms,),
    ).fetchall()
    return {r[0]: r[1] for r in rows}
