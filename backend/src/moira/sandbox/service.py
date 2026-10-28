"""Sandboxes (§11.4) and judge copies (§11.5): a private, rebased copy of the sample memory."""

import sqlite3
from pathlib import Path

import structlog

from moira import accounts
from moira.db.connection import open_db
from moira.db.repos import users as users_repo
from moira.db.repos.users import User
from moira.errors import MoiraError
from moira.memory.create import get_meta
from moira.sandbox.gc import delete_user
from moira.sandbox.rebase import delta_for, rebase
from moira.services import Services

log = structlog.get_logger()
HOUR_MS = 3_600_000


class SampleNotReady(MoiraError):
    status = 503
    code = "sample_not_ready"


def template_path(services: Services) -> Path:
    return services.settings.data_dir / "templates" / "demo.db"


def seed(services: Services, memory_path: str) -> None:
    """Copy the template with the SQLite backup API, then rebase every time."""
    src_path = template_path(services)
    if not src_path.exists():
        raise SampleNotReady("The sample memory isn’t ready yet. Try again in a minute.")
    dst_path = services.memories.path(memory_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src = open_db(src_path, readonly=True)
    dst = sqlite3.connect(dst_path)
    try:
        template_now = int(get_meta(src, "template_now") or 0)
        src.backup(dst)
        now = services.clock.now_ms()
        rebase(dst, delta_for(now, template_now), now)
    finally:
        dst.close()
        src.close()


def install(services: Services) -> None:
    """Judges and sandboxes get a seeded memory when their account is made (accounts.py)."""
    services.extras["seed_memory"] = lambda memory_path: seed(services, memory_path)


def create_sandbox(services: Services) -> User:
    """A new visitor's sandbox; evicts the oldest when the cap is reached."""
    s = services.settings
    now = services.clock.now_ms()
    while users_repo.count_kind(services.system, "sandbox", now) >= s.sandbox_max_active:
        oldest = users_repo.oldest_of_kind(services.system, "sandbox")
        if oldest is None:
            break
        delete_user(services, oldest)
        log.info("sandbox_evicted")
    if "seed_memory" not in services.extras:
        install(services)
    user = accounts.create_sandbox_user(services, now + s.sandbox_ttl_hours * HOUR_MS)
    log.info("sandbox_created")
    return user
