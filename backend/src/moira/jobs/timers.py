"""In-process timers (§7.0): they only enqueue jobs; the worker does the work.

- ``nightly``: per active memory at 03:30 in the user's time zone
- ``digest``: 08:00 Nepal time
- ``sandbox_gc``: hourly · ``tmp_sweep``: every 10 minutes · ``export_weekly``: Sunday 08:00 NPT
Global jobs are filed under the owner (``jobs.user_id`` is required).
"""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from moira.db.repos import jobs as jobs_repo
from moira.db.repos import users as users_repo
from moira.logging import get_logger
from moira.services import Services

log = get_logger(__name__)
NPT = ZoneInfo("Asia/Kathmandu")
TICK_S = 60


def crossed(prev: datetime, now: datetime, tz: ZoneInfo, hour: int, minute: int) -> bool:
    """True when the local wall-clock time hour:minute fell in (prev, now]."""
    local = now.astimezone(tz)
    mark = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if mark > local:
        mark -= timedelta(days=1)
    return prev < mark <= now


def due(services: Services, prev: datetime, now: datetime) -> list[tuple[int, str]]:
    """The (user_id, kind) jobs to enqueue for the tick (prev, now]."""
    out: list[tuple[int, str]] = []
    owner = users_repo.owner(services.system)
    for u in users_repo.all_active(services.system, int(now.timestamp() * 1000)):
        if u.kind != "sandbox" and crossed(prev, now, ZoneInfo(u.tz), 3, 30):
            out.append((u.id, "nightly"))
    if owner is not None:
        if crossed(prev, now, NPT, 8, 0):
            out.append((owner.id, "digest"))
            if now.astimezone(NPT).weekday() == 6:  # Sunday: the owner's second copy (§13.14)
                out.append((owner.id, "export_weekly"))
        if prev.replace(minute=0, second=0, microsecond=0) != now.replace(
            minute=0, second=0, microsecond=0
        ):
            out.append((owner.id, "sandbox_gc"))
        if prev.minute // 10 != now.minute // 10 or now - prev >= timedelta(minutes=10):
            out.append((owner.id, "tmp_sweep"))
    return out


def enqueue_due(services: Services, prev: datetime, now: datetime) -> int:
    n = 0
    for user_id, kind in due(services, prev, now):
        if jobs_repo.has_queued_kind(services.system, kind, user_id):
            continue  # one pending copy is enough
        services.queue.enqueue(user_id, kind, max_attempts=2)
        n += 1
    return n


async def run(services: Services) -> None:
    prev = services.clock.now()
    while True:
        await asyncio.sleep(TICK_S)
        now = services.clock.now()
        try:
            enqueue_due(services, prev, now)
        except Exception as exc:  # noqa: BLE001  # a timer must keep ticking
            log.error("timer_failed", error=type(exc).__name__)
        prev = now
