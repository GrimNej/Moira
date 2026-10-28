"""The AI usage ledger in system.db (§6.2, §9.6). One row per AI call, success or failure."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UsageRow:
    user_id: int | None
    day_utc: str
    kind: str
    model: str
    est_usd: float
    ok: bool
    created_at: int
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    web_searches: int = 0
    audio_seconds: int = 0
    prompt_version: str | None = None
    latency_ms: int | None = None


def insert(conn: sqlite3.Connection, row: UsageRow) -> None:
    conn.execute(
        "INSERT INTO usage_ledger(user_id, day_utc, kind, model, input_tokens, cached_tokens,"
        " output_tokens, reasoning_tokens, web_searches, audio_seconds, est_usd, prompt_version,"
        " latency_ms, ok, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            row.user_id,
            row.day_utc,
            row.kind,
            row.model,
            row.input_tokens,
            row.cached_tokens,
            row.output_tokens,
            row.reasoning_tokens,
            row.web_searches,
            row.audio_seconds,
            row.est_usd,
            row.prompt_version,
            row.latency_ms,
            1 if row.ok else 0,
            row.created_at,
        ),
    )


def spent_on_day(conn: sqlite3.Connection, day_utc: str, user_id: int | None = None) -> float:
    if user_id is None:
        row = conn.execute(
            "SELECT COALESCE(SUM(est_usd), 0) FROM usage_ledger WHERE day_utc = ?", (day_utc,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(est_usd), 0) FROM usage_ledger WHERE day_utc = ? AND user_id = ?",
            (day_utc, user_id),
        ).fetchone()
    return float(row[0])


def spent_by_kind_of_user(conn: sqlite3.Connection, day_utc: str, user_kind: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(l.est_usd), 0) FROM usage_ledger l JOIN users u ON u.id = l.user_id"
        " WHERE l.day_utc = ? AND u.kind = ?",
        (day_utc, user_kind),
    ).fetchone()
    return float(row[0])


def spent_total(conn: sqlite3.Connection) -> float:
    return float(conn.execute("SELECT COALESCE(SUM(est_usd), 0) FROM usage_ledger").fetchone()[0])


def count_on_day(conn: sqlite3.Connection, day_utc: str, column: str) -> int:
    if column not in ("web_searches", "audio_seconds"):
        raise ValueError(column)
    row = conn.execute(
        f"SELECT COALESCE(SUM({column}), 0) FROM usage_ledger WHERE day_utc = ?",
        (day_utc,),
    ).fetchone()
    return int(row[0])


def count_kind_on_day(conn: sqlite3.Connection, day_utc: str, kind: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM usage_ledger WHERE day_utc = ? AND kind = ? AND ok = 1",
        (day_utc, kind),
    ).fetchone()
    return int(row[0])


def summary_by_kind(conn: sqlite3.Connection, day_utc: str) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = conn.execute(
        "SELECT kind, model, COUNT(*) AS calls, SUM(est_usd) AS usd, SUM(input_tokens) AS input,"
        " SUM(cached_tokens) AS cached, SUM(output_tokens) AS output FROM usage_ledger"
        " WHERE day_utc = ? GROUP BY kind, model ORDER BY usd DESC",
        (day_utc,),
    ).fetchall()
    return rows
