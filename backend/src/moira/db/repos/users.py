"""Users, sessions, login tokens, invites and Telegram chats in system.db (§6.2)."""

import sqlite3
from dataclasses import dataclass
from typing import Literal

UserKind = Literal["owner", "tester", "judge", "sandbox"]


@dataclass(frozen=True, slots=True)
class User:
    id: int
    public_id: str
    kind: UserKind
    telegram_id: int | None
    display_name: str
    memory_path: str
    tz: str
    created_at: int
    expires_at: int | None
    disabled: bool


def _user(row: sqlite3.Row | None) -> User | None:
    if row is None:
        return None
    return User(
        id=row["id"],
        public_id=row["public_id"],
        kind=row["kind"],
        telegram_id=row["telegram_id"],
        display_name=row["display_name"],
        memory_path=row["memory_path"],
        tz=row["tz"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        disabled=bool(row["disabled"]),
    )


def create(
    conn: sqlite3.Connection,
    *,
    public_id: str,
    kind: UserKind,
    memory_path: str,
    tz: str,
    now: int,
    telegram_id: int | None = None,
    display_name: str = "",
    expires_at: int | None = None,
) -> User:
    cur = conn.execute(
        "INSERT INTO users(public_id, kind, telegram_id, display_name, memory_path, tz, created_at,"
        " expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (public_id, kind, telegram_id, display_name, memory_path, tz, now, expires_at),
    )
    user = get(conn, int(cur.lastrowid or 0))
    assert user is not None
    return user


def get(conn: sqlite3.Connection, user_id: int) -> User | None:
    return _user(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def by_public_id(conn: sqlite3.Connection, public_id: str) -> User | None:
    return _user(conn.execute("SELECT * FROM users WHERE public_id = ?", (public_id,)).fetchone())


def by_telegram_id(conn: sqlite3.Connection, telegram_id: int) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    return _user(row)


def owner(conn: sqlite3.Connection) -> User | None:
    return _user(conn.execute("SELECT * FROM users WHERE kind = 'owner' LIMIT 1").fetchone())


def set_tz(conn: sqlite3.Connection, user_id: int, tz: str) -> None:
    conn.execute("UPDATE users SET tz = ? WHERE id = ?", (tz, user_id))


def all_active(conn: sqlite3.Connection, now: int) -> list[User]:
    rows = conn.execute(
        "SELECT * FROM users WHERE disabled = 0 AND (expires_at IS NULL OR expires_at > ?)",
        (now,),
    ).fetchall()
    return [u for u in map(_user, rows) if u is not None]


def expired(conn: sqlite3.Connection, now: int, kind: UserKind) -> list[User]:
    rows = conn.execute(
        "SELECT * FROM users WHERE kind = ? AND expires_at IS NOT NULL AND expires_at <= ?",
        (kind, now),
    ).fetchall()
    return [u for u in map(_user, rows) if u is not None]


def count_kind(conn: sqlite3.Connection, kind: UserKind, now: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM users WHERE kind = ? AND (expires_at IS NULL OR expires_at > ?)",
        (kind, now),
    ).fetchone()
    return int(row[0])


def oldest_of_kind(conn: sqlite3.Connection, kind: UserKind) -> User | None:
    row = conn.execute(
        "SELECT * FROM users WHERE kind = ? ORDER BY created_at, id LIMIT 1", (kind,)
    ).fetchone()
    return _user(row)


def delete(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# Sessions ------------------------------------------------------------------


def create_session(
    conn: sqlite3.Connection, *, id_hash: str, user_id: int, now: int, expires_at: int, via: str
) -> None:
    conn.execute(
        "INSERT INTO sessions(id_hash, user_id, created_at, last_seen_at, expires_at, via)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (id_hash, user_id, now, now, expires_at, via),
    )


def session_user(conn: sqlite3.Connection, id_hash: str, now: int) -> User | None:
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.id_hash = ? AND s.expires_at > ? AND u.disabled = 0"
        " AND (u.expires_at IS NULL OR u.expires_at > ?)",
        (id_hash, now, now),
    ).fetchone()
    return _user(row)


def touch_session(conn: sqlite3.Connection, id_hash: str, now: int, expires_at: int) -> None:
    conn.execute(
        "UPDATE sessions SET last_seen_at = ?, expires_at = MAX(expires_at, ?) WHERE id_hash = ?",
        (now, expires_at, id_hash),
    )


def delete_session(conn: sqlite3.Connection, id_hash: str) -> None:
    conn.execute("DELETE FROM sessions WHERE id_hash = ?", (id_hash,))


def delete_other_sessions(conn: sqlite3.Connection, user_id: int, keep_hash: str) -> int:
    cur = conn.execute(
        "DELETE FROM sessions WHERE user_id = ? AND id_hash <> ?", (user_id, keep_hash)
    )
    return cur.rowcount


def count_sessions(conn: sqlite3.Connection, user_id: int, now: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE user_id = ? AND expires_at > ?", (user_id, now)
    ).fetchone()
    return int(row[0])


# Login tokens ----------------------------------------------------------------


def create_login_token(
    conn: sqlite3.Connection, *, token_hash: str, user_id: int, expires_at: int
) -> None:
    conn.execute(
        "INSERT INTO login_tokens(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, user_id, expires_at),
    )


def use_login_token(conn: sqlite3.Connection, token_hash: str, now: int) -> int | None:
    """Mark a token used and return its user id; None if unknown, used or expired."""
    row = conn.execute(
        "UPDATE login_tokens SET used_at = ? WHERE token_hash = ? AND used_at IS NULL"
        " AND expires_at > ? RETURNING user_id",
        (now, token_hash, now),
    ).fetchone()
    return int(row["user_id"]) if row else None


# Invites -----------------------------------------------------------------------


def create_invite(
    conn: sqlite3.Connection, *, code_hash: str, role: str, max_uses: int, expires_at: int
) -> None:
    conn.execute(
        "INSERT INTO invites(code_hash, role, max_uses, expires_at) VALUES (?, ?, ?, ?)",
        (code_hash, role, max_uses, expires_at),
    )


def use_invite(conn: sqlite3.Connection, code_hash: str, now: int) -> str | None:
    """Consume one use of an invite and return its role; None if invalid."""
    row = conn.execute(
        "UPDATE invites SET uses = uses + 1 WHERE code_hash = ? AND uses < max_uses"
        " AND expires_at > ? RETURNING role",
        (code_hash, now),
    ).fetchone()
    return str(row["role"]) if row else None


# Telegram chats ----------------------------------------------------------------


def upsert_chat(conn: sqlite3.Connection, *, chat_id: int, user_id: int, now: int) -> None:
    conn.execute(
        "INSERT INTO telegram_chats(chat_id, user_id, last_message_at) VALUES (?, ?, ?)"
        " ON CONFLICT(chat_id) DO UPDATE SET last_message_at = excluded.last_message_at",
        (chat_id, user_id, now),
    )


def chat(conn: sqlite3.Connection, chat_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM telegram_chats WHERE chat_id = ?", (chat_id,)
    ).fetchone()
    return row


def set_chat_last_nugget(conn: sqlite3.Connection, chat_id: int, nugget_pid: str | None) -> None:
    conn.execute(
        "UPDATE telegram_chats SET last_nugget_pid = ? WHERE chat_id = ?", (nugget_pid, chat_id)
    )


def set_chat_last_export(conn: sqlite3.Connection, chat_id: int, now: int) -> None:
    conn.execute("UPDATE telegram_chats SET last_export_at = ? WHERE chat_id = ?", (now, chat_id))


def chat_for_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM telegram_chats WHERE user_id = ? ORDER BY last_message_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    return row
