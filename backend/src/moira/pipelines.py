"""Pipeline job handlers beyond filing: link reading and research (§7.3, §7.5).

Each task adds its factory to ``register``; ``jobs.handlers.build`` merges them.
"""

from datetime import timedelta

from moira.ai.client import LLM
from moira.ai.research import research
from moira.db.repos import nuggets as nuggets_repo
from moira.db.repos import users as users_repo
from moira.db.repos.jobs import Job
from moira.db.repos.users import User
from moira.errors import NotFound
from moira.jobs.worker import Handler
from moira.logging import get_logger
from moira.memory import indexing
from moira.readers.base import read_link
from moira.services import Services

log = get_logger(__name__)
RETRY_DELAYS = {2: timedelta(days=1), 3: timedelta(days=7)}


def _user(services: Services, job: Job) -> User:
    user = users_repo.get(services.system, job.user_id)
    if user is None:
        raise NotFound("user gone")
    return user


def link_handlers(services: Services) -> dict[str, Handler]:
    async def read_link_job(job: Job) -> None:
        user = _user(services, job)
        conn = services.memories.open(user.memory_path)
        n = nuggets_repo.by_public_id(conn, job.ref or "")
        if n is None or n.deleted_at is not None or not n.url:
            return
        now = services.clock.now_ms()
        # A second nugget with the same canonical URL reuses the frozen reading (§7.3.2).
        reuse = nuggets_repo.research_by_canonical(conn, n.url_canonical or "")
        reuse = [r for r in reuse if r["nugget_id"] != n.id]
        if reuse:
            r = reuse[0]
            nuggets_repo.insert_research(
                conn,
                n.id,
                method=r["method"],
                status="ok",
                now=now,
                title=r["title"],
                author=r["author"],
                findings=r["findings"],
                excerpt=r["excerpt"],
                sources=__import__("json").loads(r["sources"]),
            )
            indexing.index_instant(conn, n.id, services.embedder)
            return
        reader = services.extras.get("read_link") or read_link
        res = await reader(n.url)
        if res.status == "ok":
            nuggets_repo.insert_research(
                conn,
                n.id,
                method=res.method,
                status="ok",
                now=now,
                title=res.title,
                author=res.author,
                findings=res.findings,
                excerpt=res.excerpt,
                sources=res.sources,
            )
            indexing.index_instant(conn, n.id, services.embedder)
            if n.status == "filed":
                services.queue.enqueue(user.id, "refresh", ref=n.public_id)
            return
        if res.status != "skipped":
            nuggets_repo.insert_research(conn, n.id, method=res.method, status=res.status, now=now)
        # Walled, blocked or empty: research on the web, before filing (the file job waits).
        services.queue.enqueue(user.id, "research", ref=n.public_id, payload={"attempt": 1})

    async def research_job(job: Job) -> None:
        await _research(job, int(job.payload.get("attempt", 1)))

    async def research_retry_job(job: Job) -> None:
        await _research(job, int(job.payload.get("attempt", 2)))

    async def _research(job: Job, attempt: int) -> None:
        user = _user(services, job)
        conn = services.memories.open(user.memory_path)
        n = nuggets_repo.by_public_id(conn, job.ref or "")
        if n is None or n.deleted_at is not None or not n.url:
            return
        llm: LLM = services.extras["llm"]
        res = await research(llm, n.url, n.user_text, user_id=user.id)
        now = services.clock.now_ms()
        next_retry = None
        if res.status == "not_found" and attempt + 1 in RETRY_DELAYS:
            delay = RETRY_DELAYS[attempt + 1]
            next_retry = now + int(delay.total_seconds() * 1000)
            services.queue.enqueue(
                user.id,
                "research_retry",
                ref=n.public_id,
                payload={"attempt": attempt + 1},
                delay_ms=next_retry - now,
            )
        nuggets_repo.insert_research(
            conn,
            n.id,
            method="web_search",
            status=res.status,
            now=now,
            title=res.title,
            author=res.author,
            findings=res.findings,
            sources=res.sources,
            verified=res.verified,
            searches=res.searches,
            attempt=attempt,
            next_retry_at=next_retry,
        )
        log.info("researched", status=res.status, verified=res.verified, attempt=attempt)
        if res.status == "ok":
            indexing.index_instant(conn, n.id, services.embedder)
            # A later success refreshes derived fields only; facts never change (§7.5).
            if n.status == "filed" or attempt > 1 or job.payload.get("then") == "refresh":
                services.queue.enqueue(user.id, "refresh", ref=n.public_id)

    return {
        "read_link": read_link_job,
        "research": research_job,
        "research_retry": research_retry_job,
    }


def register(services: Services) -> None:
    factories = services.extras.setdefault("handler_factories", [])
    factories.clear()
    factories.append(link_handlers)
    for extra in services.extras.get("more_factories", []):
        factories.append(extra)
