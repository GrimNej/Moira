"""The in-process job worker (§5.2, §7.0): up to WORKER_CONCURRENCY jobs at once."""

import asyncio
import contextlib
import time as _time
from collections.abc import Awaitable, Callable

from moira.db.repos.jobs import Job
from moira.jobs.queue import Queue
from moira.logging import get_logger

log = get_logger(__name__)

Handler = Callable[[Job], Awaitable[None]]


class Worker:
    def __init__(
        self,
        queue: Queue,
        handlers: dict[str, Handler],
        *,
        concurrency: int = 3,
        poll_s: float = 2.0,
    ) -> None:
        self.queue = queue
        self.handlers = handlers
        self.concurrency = concurrency
        self.poll_s = poll_s
        self._running: set[asyncio.Task[str]] = set()
        self._stopping = False

    async def execute(self, job: Job) -> str:
        """Run one claimed job and record its outcome. Returns the job's new status."""
        handler = self.handlers.get(job.kind)
        started = _time.monotonic()
        try:
            if handler is None:
                raise LookupError(f"no handler for {job.kind}")
            await handler(job)
        except Exception as exc:  # noqa: BLE001  # every failure is classified by the queue
            status = self.queue.failed(job, exc)
            log.info(
                "job_failed",
                job_id=job.id,
                kind=job.kind,
                error=type(exc).__name__,
                status=status,
                attempts=job.attempts,
            )
            return status
        self.queue.done(job)
        log.info(
            "job_done",
            job_id=job.id,
            kind=job.kind,
            duration_ms=int((_time.monotonic() - started) * 1000),
        )
        return "done"

    async def run_once(self) -> int:
        """Claim and run every ready job, respecting lanes. Returns the number run (tests)."""
        count = 0
        while True:
            job = self.queue.claim()
            if job is None:
                return count
            await self.execute(job)
            count += 1

    async def run(self) -> None:
        self.queue.requeue_stuck()
        while not self._stopping:
            while len(self._running) < self.concurrency:
                job = self.queue.claim()
                if job is None:
                    break
                task = asyncio.create_task(self.execute(job))
                self._running.add(task)
                task.add_done_callback(self._finished)
            self.queue.wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.queue.wake.wait(), timeout=self.poll_s)

    def _finished(self, task: asyncio.Task[str]) -> None:
        self._running.discard(task)
        self.queue.wake.set()

    async def stop(self, grace_s: float = 25.0) -> None:
        """Stop claiming; let running jobs finish (≤ 25 s); stuck ones re-queue at startup."""
        self._stopping = True
        self.queue.wake.set()
        if self._running:
            await asyncio.wait(self._running, timeout=grace_s)
