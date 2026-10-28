"""The job table in system.db (§6.2, §7.0). Scheduling policy lives in jobs/queue.py."""

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

# §7.0: claim one job atomically; `file` lane is FIFO with one running job per user,
# `media` lane runs one job at a time overall. The extra "no earlier queued file job" clause
# keeps capture order when debounce pushes an earlier job's run_after past a later one (Q-007).
CLAIM_SQL = """
UPDATE jobs SET status='running', locked_at=:now, attempts=attempts+1, updated_at=:now
WHERE id = (
  SELECT j.id FROM jobs j
  WHERE j.status='queued' AND j.run_after <= :now
    AND (j.lane <> 'file' OR NOT EXISTS (
          SELECT 1 FROM jobs r WHERE r.user_id=j.user_id AND r.lane='file' AND r.status='running'))
    AND (j.lane <> 'file' OR NOT EXISTS (
          SELECT 1 FROM jobs e WHERE e.user_id=j.user_id AND e.lane='file' AND e.status='queued'
            AND e.id < j.id))
    AND (j.lane <> 'media' OR NOT EXISTS (
          SELECT 1 FROM jobs m WHERE m.lane='media' AND m.status='running'))
  ORDER BY j.run_after, j.id LIMIT 1)
RETURNING *
"""


@dataclass(frozen=True, slots=True)
class Job:
    id: int
    user_id: int
    kind: str
    ref: str | None
    payload: dict[str, Any]
    lane: str
    status: str
    attempts: int
    max_attempts: int
    run_after: int
    created_at: int


def _job(row: sqlite3.Row | None) -> Job | None:
    if row is None:
        return None
    return Job(
        id=row["id"],
        user_id=row["user_id"],
        kind=row["kind"],
        ref=row["ref"],
        payload=json.loads(row["payload"]),
        lane=row["lane"],
        status=row["status"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        run_after=row["run_after"],
        created_at=row["created_at"],
    )


def insert(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    kind: str,
    lane: str,
    run_after: int,
    now: int,
    ref: str | None = None,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 5,
) -> int:
    cur = conn.execute(
        "INSERT INTO jobs(user_id, kind, ref, payload, lane, max_attempts, run_after, created_at,"
        " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, kind, ref, json.dumps(payload or {}), lane, max_attempts, run_after, now, now),
    )
    return int(cur.lastrowid or 0)


def get(conn: sqlite3.Connection, job_id: int) -> Job | None:
    return _job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def claim(conn: sqlite3.Connection, now: int) -> Job | None:
    return _job(conn.execute(CLAIM_SQL, {"now": now}).fetchone())


def finish(conn: sqlite3.Connection, job_id: int, now: int) -> None:
    conn.execute(
        "UPDATE jobs SET status='done', locked_at=NULL, updated_at=? WHERE id=?", (now, job_id)
    )


def reschedule(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    run_after: int,
    now: int,
    error: str | None = None,
    refund_attempt: bool = False,
) -> None:
    """Back to the queue. ``refund_attempt`` undoes the claim's attempt (budget/outage, §9.10)."""
    conn.execute(
        "UPDATE jobs SET status='queued', locked_at=NULL, run_after=?, last_error=?,"
        " attempts = attempts - ?, updated_at=? WHERE id=?",
        (run_after, error, 1 if refund_attempt else 0, now, job_id),
    )


def mark(conn: sqlite3.Connection, job_id: int, status: str, now: int, error: str | None) -> None:
    conn.execute(
        "UPDATE jobs SET status=?, locked_at=NULL, last_error=?, updated_at=? WHERE id=?",
        (status, error, now, job_id),
    )


def requeue_stuck(conn: sqlite3.Connection, *, older_than: int, now: int) -> int:
    cur = conn.execute(
        "UPDATE jobs SET status='queued', locked_at=NULL, run_after=?, updated_at=?"
        " WHERE status='running' AND locked_at < ?",
        (now, now, older_than),
    )
    return cur.rowcount


def queued_for_ref(conn: sqlite3.Connection, user_id: int, ref: str, kind: str) -> Job | None:
    row = conn.execute(
        "SELECT * FROM jobs WHERE user_id=? AND ref=? AND kind=? AND status='queued'"
        " ORDER BY id DESC LIMIT 1",
        (user_id, ref, kind),
    ).fetchone()
    return _job(row)


def pending_for_ref(
    conn: sqlite3.Connection, user_id: int, ref: str, kinds: tuple[str, ...]
) -> list[Job]:
    marks = ",".join("?" * len(kinds))
    rows = conn.execute(
        f"SELECT * FROM jobs WHERE user_id=? AND ref=? AND kind IN ({marks})"
        " AND status IN ('queued','running')",
        (user_id, ref, *kinds),
    ).fetchall()
    return [j for j in map(_job, rows) if j is not None]


def set_run_after(conn: sqlite3.Connection, job_id: int, run_after: int, now: int) -> None:
    conn.execute(
        "UPDATE jobs SET run_after=?, updated_at=? WHERE id=? AND status='queued'",
        (run_after, now, job_id),
    )


def cancel_for_ref(conn: sqlite3.Connection, user_id: int, ref: str, now: int) -> int:
    cur = conn.execute(
        "UPDATE jobs SET status='cancelled', updated_at=? WHERE user_id=? AND ref=?"
        " AND status='queued'",
        (now, user_id, ref),
    )
    return cur.rowcount


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def dead_since(conn: sqlite3.Connection, since: int) -> list[Job]:
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status='dead' AND updated_at >= ? ORDER BY id", (since,)
    ).fetchall()
    return [j for j in map(_job, rows) if j is not None]


def has_queued_kind(conn: sqlite3.Connection, kind: str, user_id: int | None = None) -> bool:
    if user_id is None:
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE kind=? AND status IN ('queued','running') LIMIT 1", (kind,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE kind=? AND user_id=? AND status IN ('queued','running')"
            " LIMIT 1",
            (kind, user_id),
        ).fetchone()
    return row is not None
