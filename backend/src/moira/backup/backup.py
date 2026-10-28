"""Nightly encrypted backup (§13.14): ``python -m moira.backup.backup``.

A separate short-lived process (systemd timer), so the app is never disturbed:
snapshot with the SQLite online backup API → integrity_check → tar | zstd -19 | age →
rclone to daily/ (and weekly/ on Sundays) → retention → record → delete staging.
Sandboxes and the demo template are not backed up.
"""

import json
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx

from moira.clock import Clock, SystemClock
from moira.config import Settings, load_settings
from moira.logging import configure_logging, get_logger
from moira.memory.create import set_meta

log = get_logger(__name__)
Runner = Callable[[Sequence[str]], None]


class BackupFailed(Exception):
    pass


def run(cmd: Sequence[str]) -> None:
    subprocess.run(list(cmd), check=True)


def sources(data_dir: Path) -> list[Path]:
    """system.db and every user memory; never sandboxes or templates."""
    out = [data_dir / "system.db"]
    out += sorted((data_dir / "memories").glob("*.db"))
    return [p for p in out if p.exists()]


def snapshot(data_dir: Path, staging: Path) -> list[Path]:
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    taken = []
    for src in sources(data_dir):
        rel = src.relative_to(data_dir)
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        a, b = sqlite3.connect(f"file:{src}?mode=ro", uri=True), sqlite3.connect(dst)
        try:
            a.backup(b)  # consistent even while the app writes
        finally:
            b.close()
            a.close()
        taken.append(dst)
    return taken


def check_integrity(paths: list[Path]) -> None:
    for p in paths:
        conn = sqlite3.connect(p)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        if result != "ok":
            raise BackupFailed(f"integrity_check failed for {p.name}")


def archive(staging: Path, out: Path, recipient: str) -> None:
    """tar | zstd -19 | age -r <recipient> -o <out> (no shell, no plaintext on disk)."""
    tar = subprocess.Popen(["tar", "-C", str(staging), "-cf", "-", "."], stdout=subprocess.PIPE)
    zstd = subprocess.Popen(["zstd", "-19", "-q", "-c"], stdin=tar.stdout, stdout=subprocess.PIPE)
    assert tar.stdout is not None and zstd.stdout is not None
    tar.stdout.close()
    age = subprocess.Popen(["age", "-r", recipient, "-o", str(out)], stdin=zstd.stdout)
    zstd.stdout.close()
    codes = (age.wait(), zstd.wait(), tar.wait())
    if any(codes):
        out.unlink(missing_ok=True)
        raise BackupFailed(f"archive pipeline exited with {codes}")


def upload(out: Path, remote: str, *, sunday: bool, settings: Settings, runner: Runner) -> None:
    runner(["rclone", "copy", str(out), f"{remote}/daily/"])
    if sunday:
        runner(["rclone", "copy", str(out), f"{remote}/weekly/"])
    # Retention: 14 daily, 8 weekly. This is also how forgotten data ages out (§10.4).
    runner(["rclone", "delete", "--min-age", f"{settings.backup_keep_daily}d", f"{remote}/daily/"])
    runner(
        [
            "rclone",
            "delete",
            "--min-age",
            f"{settings.backup_keep_weekly * 7}d",
            f"{remote}/weekly/",
        ]
    )


def record(data_dir: Path, when: datetime, size: int, status: str) -> None:
    marker = data_dir / "backups" / "last.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"when": when.strftime("%Y-%m-%d %H:%M UTC"), "status": status, "bytes": size}),
        encoding="utf-8",
    )
    system = data_dir / "system.db"
    if status == "ok" and system.exists():
        conn = sqlite3.connect(system)
        try:
            with conn:
                set_meta(conn, "last_backup_at", str(int(when.timestamp() * 1000)))
                set_meta(conn, "last_backup_bytes", str(size))
        finally:
            conn.close()


def alert(settings: Settings, text: str) -> None:
    """The owner hears at once when a backup fails (§13.15). Best effort."""
    token = settings.telegram_bot_token.get_secret_value()
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": settings.owner_telegram_id, "text": text},
            timeout=15,
        )
    except httpx.HTTPError:
        log.error("backup_alert_failed")


def backup(settings: Settings, clock: Clock, runner: Runner = run) -> Path:
    if not settings.backup_age_recipient or not settings.backup_rclone_remote:
        raise BackupFailed("BACKUP_AGE_RECIPIENT and BACKUP_RCLONE_REMOTE must be set")
    data_dir = settings.data_dir
    now = clock.now().astimezone(UTC)
    staging = data_dir / "backups" / "staging"
    out = data_dir / "backups" / f"moira-{now.date().isoformat()}.tar.zst.age"
    try:
        check_integrity(snapshot(data_dir, staging))
        archive(staging, out, settings.backup_age_recipient)
        upload(
            out,
            settings.backup_rclone_remote,
            sunday=now.weekday() == 6,
            settings=settings,
            runner=runner,
        )
        size = out.stat().st_size
        record(data_dir, now, size, "ok")
        log.info("backup_done", bytes=size)
        return out
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        out.unlink(missing_ok=True)  # the copy lives in object storage


def main() -> int:
    settings = load_settings()
    configure_logging()
    clock = SystemClock()
    try:
        backup(settings, clock)
    except (BackupFailed, subprocess.CalledProcessError, OSError, sqlite3.Error) as exc:
        record(settings.data_dir, clock.now().astimezone(UTC), 0, "failed")
        log.error("backup_failed", error=type(exc).__name__)
        alert(
            settings, f"Moira: last night's backup failed ({type(exc).__name__}). See the journal."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
