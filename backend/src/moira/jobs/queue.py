"""Job scheduling policy (§7.0, §9.10): lanes, debounce, backoff, rescheduling rules."""

import asyncio
import random
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from moira.clock import Clock, from_ms, to_ms
from moira.db.repos import jobs as repo
from moira.db.repos.jobs import Job
from moira.errors import (
    AiBudgetExceeded,
    AiInvalidOutput,
    AiRejected,
    AiTransient,
    AiUnavailable,
    Reschedule,
)
from moira.logging import get_logger

log = get_logger(__name__)

LANES: dict[str, str] = {
    "read_link": "default",
    "research": "default",
    "research_retry": "default",
    "transcribe": "media",
    "read_video": "media",
    "read_pdf": "media",
    "file": "file",
    "refresh": "file",
    "edit_refile": "file",
    "hard_delete": "default",
    "nightly": "file",
    "sandbox_gc": "default",
    "tmp_sweep": "default",
    "digest": "default",
    "export_weekly": "default",
}
DEBOUNCE_MS = 20_000
DEBOUNCE_MAX_MS = 90_000
STUCK_MS = 10 * 60_000
LIFETIME_RECHECK_MS = 60 * 60_000


def backoff_ms(attempts: int, rng: random.Random) -> int:
    """15 s × 2^(attempts−1) ± 20 % jitter."""
    base = 15_000 * 2 ** max(0, attempts - 1)
    return int(base * rng.uniform(0.8, 1.2))


class Queue:
    def __init__(
        self, conn: sqlite3.Connection, clock: Clock, rng: random.Random | None = None
    ) -> None:
        self.conn = conn
        self.clock = clock
        self.rng = rng or random.Random()  # noqa: S311  # jitter, not security
        self.wake = asyncio.Event()

    def enqueue(
        self,
        user_id: int,
        kind: str,
        *,
        ref: str | None = None,
        payload: dict[str, Any] | None = None,
        delay_ms: int = 0,
        max_attempts: int = 5,
    ) -> int:
        now = self.clock.now_ms()
        job_id = repo.insert(
            self.conn,
            user_id=user_id,
            kind=kind,
            lane=LANES.get(kind, "default"),
            run_after=now + delay_ms,
            now=now,
            ref=ref,
            payload=payload,
            max_attempts=max_attempts,
        )
        self.wake.set()
        return job_id

    def enqueue_file(self, user_id: int, ref: str, first_message_at: int) -> int:
        """Create or bump the debounced ``file`` job of a nugget (§7.0 debounce)."""
        now = self.clock.now_ms()
        run_after = min(now + DEBOUNCE_MS, first_message_at + DEBOUNCE_MAX_MS)
        existing = repo.queued_for_ref(self.conn, user_id, ref, "file")
        if existing is not None:
            repo.set_run_after(self.conn, existing.id, run_after, now)
            return existing.id
        return self.enqueue(
            user_id,
            "file",
            ref=ref,
            payload={"first_message_at": first_message_at},
            delay_ms=run_after - now,
        )

    def file_job_open(self, user_id: int, ref: str) -> bool:
        """Grouping rule 1 (§7.1.1): the nugget's file job is still queued."""
        return repo.queued_for_ref(self.conn, user_id, ref, "file") is not None

    def claim(self) -> Job | None:
        return repo.claim(self.conn, self.clock.now_ms())

    def done(self, job: Job) -> None:
        repo.finish(self.conn, job.id, self.clock.now_ms())

    def requeue_stuck(self) -> int:
        now = self.clock.now_ms()
        n = repo.requeue_stuck(self.conn, older_than=now - STUCK_MS, now=now)
        if n:
            log.warning("jobs_requeued", count=n)
        return n

    def failed(self, job: Job, exc: BaseException) -> str:
        """Decide what happens after a job raised. Returns the new status."""
        now = self.clock.now_ms()
        name = type(exc).__name__
        if isinstance(exc, Reschedule):
            repo.reschedule(
                self.conn,
                job.id,
                run_after=now + int(exc.delay_s * 1000),
                now=now,
                refund_attempt=True,
            )
            return "queued"
        if isinstance(exc, AiBudgetExceeded):
            if exc.lifetime:
                run_after = now + LIFETIME_RECHECK_MS
            else:
                today = from_ms(now).astimezone(UTC).date()
                midnight = datetime(today.year, today.month, today.day, tzinfo=UTC) + timedelta(1)
                run_after = to_ms(midnight) + int(self.rng.uniform(0, 30 * 60_000))
            repo.reschedule(
                self.conn, job.id, run_after=run_after, now=now, error=name, refund_attempt=True
            )
            return "queued"
        if isinstance(exc, AiUnavailable):
            repo.reschedule(
                self.conn,
                job.id,
                run_after=now + int(exc.retry_after_s * 1000),
                now=now,
                error=name,
                refund_attempt=True,
            )
            return "queued"
        if isinstance(exc, AiRejected | AiInvalidOutput) or job.attempts >= job.max_attempts:
            status = "dead" if job.attempts >= job.max_attempts else "failed"
            if isinstance(exc, AiRejected | AiInvalidOutput):
                status = "dead"
            repo.mark(self.conn, job.id, status, now, name)
            log.warning("job_dead", job_id=job.id, kind=job.kind, error=name)
            return status
        delay = backoff_ms(job.attempts, self.rng)
        if isinstance(exc, AiTransient) and exc.retry_after_s:
            delay = max(delay, int(exc.retry_after_s * 1000))
        repo.reschedule(self.conn, job.id, run_after=now + delay, now=now, error=name)
        return "queued"
