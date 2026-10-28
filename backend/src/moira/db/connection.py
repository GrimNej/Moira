"""SQLite connections (blueprint §6.1, §5.6).

Every connection gets the same pragmas and, when the Python build allows it, sqlite-vec.
If extensions cannot load, ``vec_available()`` is False and ``search/vectors.py`` uses the
numpy fallback. One ``asyncio.Lock`` per database file serialises writes.
"""

import asyncio
import sqlite3
from pathlib import Path

from moira.logging import get_logger

log = get_logger(__name__)

PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -16000",
)

_vec_state: bool | None = None
_write_locks: dict[str, asyncio.Lock] = {}


def _load_vec(conn: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except (AttributeError, ImportError, sqlite3.OperationalError):
        return False


def vec_available() -> bool:
    """Whether sqlite-vec loads in this Python (checked once, logged once)."""
    global _vec_state
    if _vec_state is None:
        probe = sqlite3.connect(":memory:")
        _vec_state = _load_vec(probe)
        probe.close()
        log.info("sqlite_vec", available=_vec_state, sqlite=sqlite3.sqlite_version)
        if not _vec_state:
            log.warning("sqlite_vec_fallback", using="numpy brute-force vectors")
    return _vec_state


def open_db(path: Path | str, *, readonly: bool = False) -> sqlite3.Connection:
    """Open a database with the §6.1 pragmas. Rows come back as ``sqlite3.Row``."""
    target = str(path)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        conn = sqlite3.connect(
            f"file:{Path(target).as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
    else:
        conn = sqlite3.connect(target, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        if readonly and "journal_mode" in pragma:
            continue
        conn.execute(pragma)
    if vec_available():
        _load_vec(conn)
    return conn


def write_lock(path: Path | str) -> asyncio.Lock:
    """The single write lock for one database file."""
    key = str(Path(path).resolve()) if str(path) != ":memory:" else ":memory:"
    lock = _write_locks.get(key)
    if lock is None:
        lock = _write_locks[key] = asyncio.Lock()
    return lock


class Tx:
    """``with Tx(conn): ...`` runs a BEGIN IMMEDIATE … COMMIT/ROLLBACK block."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.conn.execute("COMMIT" if exc_type is None else "ROLLBACK")
