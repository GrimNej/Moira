"""T13: job queue and worker with FixedClock (§7.0, §9.10)."""

import random
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from moira.clock import FixedClock, to_ms
from moira.db.connection import open_db
from moira.db.migrate import migrate
from moira.db.repos import jobs as repo
from moira.db.repos import users
from moira.db.repos.jobs import Job
from moira.errors import AiBudgetExceeded, AiRejected, AiTransient, AiUnavailable, Reschedule
from moira.jobs.queue import Queue, backoff_ms
from moira.jobs.worker import Worker

T0 = datetime(2026, 10, 26, 15, 15, tzinfo=UTC)


@pytest.fixture
def env(tmp_path: Path) -> tuple[sqlite3.Connection, FixedClock, Queue, int, int]:
    conn = open_db(tmp_path / "system.db")
    migrate(conn, "system")
    clock = FixedClock(T0)
    q = Queue(conn, clock, rng=random.Random(7))
    a = users.create(
        conn, public_id="u_aaaaaaaaaaaa", kind="owner", memory_path="a", tz="UTC", now=0
    )
    b = users.create(
        conn, public_id="u_bbbbbbbbbbbb", kind="tester", memory_path="b", tz="UTC", now=0
    )
    return conn, clock, q, a.id, b.id


def test_claim_takes_exactly_one_job(env) -> None:  # type: ignore[no-untyped-def]
    conn, _clock, q, a, _ = env
    q.enqueue(a, "read_link", ref="n_1")
    q.enqueue(a, "read_link", ref="n_2")
    first = q.claim()
    second = q.claim()
    assert first is not None and second is not None and first.id != second.id
    assert q.claim() is None
    assert repo.get(conn, first.id).status == "running"  # type: ignore[union-attr]


def test_file_lane_is_fifo_per_user(env) -> None:  # type: ignore[no-untyped-def]
    _, _clock, q, a, b = env
    j1 = q.enqueue(a, "file", ref="n_1")
    j2 = q.enqueue(a, "file", ref="n_2")
    j3 = q.enqueue(b, "file", ref="n_3")
    got = q.claim()
    assert got is not None and got.id == j1
    other = q.claim()
    assert other is not None and other.id == j3  # another user's file job may run
    assert q.claim() is None  # j2 waits for j1
    q.done(got)
    nxt = q.claim()
    assert nxt is not None and nxt.id == j2


def test_file_order_survives_debounce(env) -> None:  # type: ignore[no-untyped-def]
    _, clock, q, a, _ = env
    first_at = clock.now_ms()
    j1 = q.enqueue_file(a, "n_1", first_at)
    clock.advance(timedelta(seconds=5))
    j2 = q.enqueue_file(a, "n_2", clock.now_ms())
    clock.advance(timedelta(seconds=10))
    q.enqueue_file(a, "n_1", first_at)  # a caption joins n_1: its job moves later than j2's
    clock.advance(timedelta(seconds=16))  # j2 is due, j1 is not yet
    assert q.claim() is None  # j2 must not overtake j1
    clock.advance(timedelta(seconds=20))
    got = q.claim()
    assert got is not None and got.id == j1
    q.done(got)
    got2 = q.claim()
    assert got2 is not None and got2.id == j2


def test_media_lane_runs_one_at_a_time(env) -> None:  # type: ignore[no-untyped-def]
    _, _, q, a, b = env
    q.enqueue(a, "transcribe", ref="n_1")
    q.enqueue(b, "transcribe", ref="n_2")
    first = q.claim()
    assert first is not None and first.lane == "media"
    assert q.claim() is None
    q.done(first)
    assert q.claim() is not None


def test_backoff_then_dead(env) -> None:  # type: ignore[no-untyped-def]
    conn, clock, q, a, _ = env
    jid = q.enqueue(a, "read_link", ref="n_1", max_attempts=3)
    delays = []
    for attempt in (1, 2):
        job = q.claim()
        assert job is not None and job.attempts == attempt
        assert q.failed(job, AiTransient("x")) == "queued"
        row = repo.get(conn, jid)
        assert row is not None
        delays.append(row.run_after - clock.now_ms())
        clock.advance(timedelta(milliseconds=row.run_after - clock.now_ms()))
    assert 12_000 <= delays[0] <= 18_000
    assert 24_000 <= delays[1] <= 36_000
    job = q.claim()
    assert job is not None
    assert q.failed(job, AiTransient("x")) == "dead"
    assert repo.get(conn, jid).status == "dead"  # type: ignore[union-attr]


def test_backoff_formula() -> None:
    rng = random.Random(1)
    for attempts in range(1, 6):
        base = 15_000 * 2 ** (attempts - 1)
        assert 0.8 * base <= backoff_ms(attempts, rng) <= 1.2 * base


def test_rejected_output_is_dead_at_once(env) -> None:  # type: ignore[no-untyped-def]
    _, _, q, a, _ = env
    q.enqueue(a, "file", ref="n_1")
    job = q.claim()
    assert job is not None
    assert q.failed(job, AiRejected("400")) == "dead"


def test_retry_after_is_honored(env) -> None:  # type: ignore[no-untyped-def]
    conn, clock, q, a, _ = env
    jid = q.enqueue(a, "read_link")
    job = q.claim()
    assert job is not None
    q.failed(job, AiTransient("429", retry_after_s=300))
    assert repo.get(conn, jid).run_after == clock.now_ms() + 300_000  # type: ignore[union-attr]


def test_debounce_moves_run_after_with_a_90_second_cap(env) -> None:  # type: ignore[no-untyped-def]
    conn, clock, q, a, _ = env
    first = clock.now_ms()
    jid = q.enqueue_file(a, "n_1", first)
    assert repo.get(conn, jid).run_after == first + 20_000  # type: ignore[union-attr]
    for _ in range(8):
        clock.advance(timedelta(seconds=15))
        assert q.enqueue_file(a, "n_1", first) == jid
    job = repo.get(conn, jid)
    assert job is not None and job.run_after == first + 90_000


def test_stuck_running_jobs_requeue_at_startup(env) -> None:  # type: ignore[no-untyped-def]
    conn, clock, q, a, _ = env
    jid = q.enqueue(a, "read_link")
    assert q.claim() is not None
    clock.advance(timedelta(minutes=11))
    assert q.requeue_stuck() == 1
    assert repo.get(conn, jid).status == "queued"  # type: ignore[union-attr]


def test_budget_reschedules_to_next_utc_day_without_using_an_attempt(env) -> None:  # type: ignore[no-untyped-def]
    conn, _clock, q, a, _ = env
    jid = q.enqueue(a, "file", ref="n_1")
    job = q.claim()
    assert job is not None and job.attempts == 1
    q.failed(job, AiBudgetExceeded("cap"))
    row = repo.get(conn, jid)
    assert row is not None and row.attempts == 0 and row.status == "queued"
    midnight = to_ms(datetime(2026, 10, 27, tzinfo=UTC))
    assert midnight <= row.run_after <= midnight + 30 * 60_000


def test_lifetime_cap_keeps_jobs_queued(env) -> None:  # type: ignore[no-untyped-def]
    conn, _clock, q, a, _ = env
    jid = q.enqueue(a, "file", ref="n_1")
    job = q.claim()
    assert job is not None
    q.failed(job, AiBudgetExceeded("total", lifetime=True))
    row = repo.get(conn, jid)
    assert row is not None and row.status == "queued" and row.attempts == 0


def test_outage_reschedules_after_breaker_without_attempt(env) -> None:  # type: ignore[no-untyped-def]
    conn, clock, q, a, _ = env
    jid = q.enqueue(a, "file", ref="n_1")
    job = q.claim()
    assert job is not None
    q.failed(job, AiUnavailable("open", retry_after_s=120))
    row = repo.get(conn, jid)
    assert row is not None and row.attempts == 0
    assert row.run_after == clock.now_ms() + 120_000


async def test_worker_runs_handlers_and_reschedules(env) -> None:  # type: ignore[no-untyped-def]
    conn, _clock, q, a, _ = env
    seen: list[str] = []

    async def ok(job: Job) -> None:
        seen.append(job.ref or "")

    async def later(job: Job) -> None:
        raise Reschedule(5)

    w = Worker(q, {"read_link": ok, "file": later})
    q.enqueue(a, "read_link", ref="n_1")
    fid = q.enqueue(a, "file", ref="n_2")
    assert await w.run_once() == 2
    assert seen == ["n_1"]
    row = repo.get(conn, fid)
    assert row is not None and row.status == "queued" and row.attempts == 0
