"""T08: system.db migration, pragmas, idempotent migrations, sqlite-vec or fallback."""

import sqlite3
from pathlib import Path

import pytest

from moira.db import connection
from moira.db.connection import open_db, vec_available
from moira.db.migrate import migrate, migrate_file, schema_version
from moira.db.repos import jobs, usage, users

SYSTEM_TABLES = {
    "meta",
    "users",
    "sessions",
    "login_tokens",
    "invites",
    "jobs",
    "usage_ledger",
    "telegram_chats",
}


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table')").fetchall()
    return {r["name"] for r in rows}


@pytest.fixture
def sysdb(tmp_path: Path) -> sqlite3.Connection:
    conn = open_db(tmp_path / "system.db")
    migrate(conn, "system")
    return conn


def test_migration_creates_every_table(sysdb: sqlite3.Connection) -> None:
    assert tables(sysdb) >= SYSTEM_TABLES
    assert schema_version(sysdb) == 1


def test_pragmas_are_set_on_every_connection(tmp_path: Path) -> None:
    for _ in range(2):
        conn = open_db(tmp_path / "p.db")
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
        assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2  # MEMORY
        assert conn.execute("PRAGMA cache_size").fetchone()[0] == -16000
        conn.close()


def test_running_migrations_twice_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "system.db"
    migrate_file(path, "system")
    conn = open_db(path)
    before = conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    assert migrate(conn, "system") == 1
    after = conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_sqlite_vec_loads_or_fallback_is_selected() -> None:
    conn = open_db(":memory:")
    if vec_available():
        assert conn.execute("SELECT vec_version()").fetchone()[0].startswith("v")
    else:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT vec_version()")


def test_fallback_is_used_when_extensions_cannot_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection, "_vec_state", False)
    from moira.db.migrate import render

    sql = render(
        "CREATE VIRTUAL TABLE vec_x USING vec0(embedding float[{embed_dim}]);", embed_dim=8
    )
    assert sql == "CREATE TABLE vec_x (rowid INTEGER PRIMARY KEY, embedding BLOB NOT NULL);"


def test_users_sessions_tokens_invites(sysdb: sqlite3.Connection) -> None:
    u = users.create(
        sysdb, public_id="u_aaaaaaaaaaaa", kind="owner", memory_path="m.db", tz="UTC", now=1000
    )
    assert users.by_public_id(sysdb, "u_aaaaaaaaaaaa") == u
    users.create_session(sysdb, id_hash="h", user_id=u.id, now=1000, expires_at=5000, via="sandbox")
    assert users.session_user(sysdb, "h", 2000) == u
    assert users.session_user(sysdb, "h", 6000) is None
    users.create_login_token(sysdb, token_hash="t", user_id=u.id, expires_at=3000)
    assert users.use_login_token(sysdb, "t", 2000) == u.id
    assert users.use_login_token(sysdb, "t", 2001) is None  # works once
    users.create_invite(sysdb, code_hash="c", role="judge", max_uses=1, expires_at=9000)
    assert users.use_invite(sysdb, "c", 100) == "judge"
    assert users.use_invite(sysdb, "c", 100) is None


def test_jobs_and_usage_round_trip(sysdb: sqlite3.Connection) -> None:
    u = users.create(
        sysdb, public_id="u_bbbbbbbbbbbb", kind="tester", memory_path="m", tz="UTC", now=1
    )
    jid = jobs.insert(sysdb, user_id=u.id, kind="file", lane="file", run_after=10, now=1, ref="n_x")
    assert jobs.claim(sysdb, 5) is None
    job = jobs.claim(sysdb, 10)
    assert job is not None and job.id == jid and job.attempts == 1
    usage.insert(
        sysdb,
        usage.UsageRow(
            user_id=u.id,
            day_utc="2026-10-28",
            kind="enrich",
            model="m",
            est_usd=0.25,
            ok=True,
            created_at=1,
        ),
    )
    assert usage.spent_on_day(sysdb, "2026-10-28") == 0.25
    assert usage.spent_on_day(sysdb, "2026-10-28", u.id) == 0.25
    assert usage.spent_by_kind_of_user(sysdb, "2026-10-28", "tester") == 0.25
