"""Forward-only migrations (blueprint §6, §13.13).

Migration files live in ``migrations/<kind>/NNNN_name.sql``; ``meta.schema_version`` records
the last one applied. Memory migrations may use ``{embed_dim}``. When sqlite-vec is not
available, ``vec0`` tables become plain tables that the numpy fallback reads.

CLI (the deploy script runs it): ``python -m moira.db.migrate --all`` migrates system.db and
every memory database under DATA_DIR, snapshotting each existing file first.
"""

import re
import sqlite3
import sys
from pathlib import Path
from typing import Literal

from moira.db.connection import open_db, vec_available
from moira.logging import get_logger

log = get_logger(__name__)

Kind = Literal["system", "memory"]
MIGRATIONS = Path(__file__).parent / "migrations"
VEC_RE = re.compile(
    r"CREATE VIRTUAL TABLE (\w+)\s+USING vec0\(embedding float\[\d+\]\);", re.IGNORECASE
)


def migration_files(kind: Kind) -> list[tuple[int, Path]]:
    files = []
    for path in sorted((MIGRATIONS / kind).glob("*.sql")):
        files.append((int(path.name.split("_", 1)[0]), path))
    return files


def schema_version(conn: sqlite3.Connection) -> int:
    has_meta = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'"
    ).fetchone()
    if not has_meta:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row["value"]) if row else 0


def render(sql: str, *, embed_dim: int) -> str:
    sql = sql.replace("{embed_dim}", str(embed_dim))
    if not vec_available():
        sql = VEC_RE.sub(
            r"CREATE TABLE \1 (rowid INTEGER PRIMARY KEY, embedding BLOB NOT NULL);", sql
        )
    return sql


def migrate(conn: sqlite3.Connection, kind: Kind, *, embed_dim: int = 256) -> int:
    """Apply every newer migration in one transaction each. Returns the new version."""
    current = schema_version(conn)
    for number, path in migration_files(kind):
        if number <= current:
            continue
        sql = render(path.read_text(encoding="utf-8"), embed_dim=embed_dim)
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in split_sql(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(number),),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        log.info("migrated", kind=kind, version=number)
        current = number
    return current


def split_sql(sql: str) -> list[str]:
    """Split a migration into statements (no triggers in our migrations, so ';' is enough)."""
    lines = [line.split("--", 1)[0] for line in sql.splitlines()]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def snapshot(path: Path) -> Path:
    """Copy a database with the online backup API before migrating it."""
    target = path.with_suffix(path.suffix + f".pre-migrate-v{_version_of(path)}")
    src = sqlite3.connect(path)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return target


def _version_of(path: Path) -> int:
    conn = open_db(path)
    try:
        return schema_version(conn)
    finally:
        conn.close()


def migrate_file(path: Path, kind: Kind, *, embed_dim: int = 256) -> int:
    latest = migration_files(kind)[-1][0]
    if path.exists() and _version_of(path) < latest:
        snapshot(path)
    conn = open_db(path)
    try:
        return migrate(conn, kind, embed_dim=embed_dim)
    finally:
        conn.close()


def migrate_all(data_dir: Path, *, embed_dim: int = 256) -> None:
    migrate_file(data_dir / "system.db", "system")
    for folder in ("memories", "sandboxes", "templates"):
        for db in sorted((data_dir / folder).glob("*.db")):
            migrate_file(db, "memory", embed_dim=embed_dim)


def main(argv: list[str]) -> int:
    from moira.config import load_settings
    from moira.logging import configure_logging

    settings = load_settings()
    configure_logging(settings.log_level, json=settings.app_env == "prod")
    if argv != ["--all"]:
        print("usage: python -m moira.db.migrate --all", file=sys.stderr)  # noqa: T201
        return 2
    migrate_all(settings.data_dir, embed_dim=settings.embed_dim)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
