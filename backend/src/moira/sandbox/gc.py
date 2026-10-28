"""Expired sandboxes are deleted hourly: the file, the user, their sessions and jobs (§11.4)."""

import structlog

from moira.db.repos import users as users_repo
from moira.db.repos.users import User
from moira.services import Services

log = structlog.get_logger()


def delete_user(services: Services, user: User) -> None:
    services.memories.close(user.memory_path)
    path = services.memories.path(user.memory_path)
    for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        p.unlink(missing_ok=True)
    with services.system:
        users_repo.delete(services.system, user.id)  # sessions and jobs cascade


def sandbox_gc(services: Services) -> int:
    now = services.clock.now_ms()
    gone = users_repo.expired(services.system, now, "sandbox")
    for u in gone:
        delete_user(services, u)
    if gone:
        log.info("sandbox_gc", deleted=len(gone))
    return len(gone)
