"""Job handlers by kind (§7.0). Each handler is a closure over the services."""

from datetime import timedelta

from moira.ai.client import LLM
from moira.db.repos import jobs as jobs_repo
from moira.db.repos import nuggets as nuggets_repo
from moira.db.repos import users as users_repo
from moira.db.repos.jobs import Job
from moira.db.repos.users import User
from moira.errors import NotFound, Reschedule
from moira.jobs.worker import Handler
from moira.logging import get_logger
from moira.memory import filing, forget
from moira.services import Services

log = get_logger(__name__)

PRE_FILE_KINDS = ("read_link", "transcribe", "read_video", "read_pdf")
PRECONDITION_WAIT_MS = 3 * 60_000


def _user(services: Services, job: Job) -> User:
    user = users_repo.get(services.system, job.user_id)
    if user is None:
        raise NotFound("user gone")
    return user


def build(services: Services) -> dict[str, Handler]:
    def llm() -> LLM:
        client: LLM = services.extras["llm"]
        return client

    async def file_job(job: Job) -> None:
        user = _user(services, job)
        assert job.ref is not None
        pending = [
            j
            for j in jobs_repo.pending_for_ref(services.system, user.id, job.ref, PRE_FILE_KINDS)
            if j.id != job.id
        ]
        first_research = [
            j
            for j in jobs_repo.pending_for_ref(services.system, user.id, job.ref, ("research",))
            if j.attempts <= 1
        ]
        waited = services.clock.now_ms() - job.created_at
        if (pending or first_research) and waited < PRECONDITION_WAIT_MS:
            raise Reschedule(5)
        done = await filing.file_nugget(services, llm(), user, job.ref, mode="file")
        if done is not None and done.needs_research:
            conn = services.memories.open(user.memory_path)
            n = nuggets_repo.by_public_id(conn, job.ref)
            has_research = n is not None and any(
                r["method"] == "web_search" for r in nuggets_repo.research_for(conn, n.id)
            )
            if n is not None and n.url and not has_research:
                services.queue.enqueue(
                    user.id, "research", ref=job.ref, payload={"then": "refresh"}
                )

    async def refresh_job(job: Job) -> None:
        user = _user(services, job)
        assert job.ref is not None
        await filing.file_nugget(services, llm(), user, job.ref, mode="refresh")

    async def edit_refile_job(job: Job) -> None:
        user = _user(services, job)
        assert job.ref is not None
        await filing.file_nugget(services, llm(), user, job.ref, mode="edit_refile")

    async def hard_delete_job(job: Job) -> None:
        user = _user(services, job)
        conn = services.memories.open(user.memory_path)
        n = nuggets_repo.by_public_id(conn, job.ref or "")
        if n is None:
            return
        rebuild = services.extras.get("rebuild_now")
        async with services.memories.lock(user.memory_path):
            forget.hard_delete(conn, n.id, now=services.clock.now_ms(), rebuild_now=rebuild)

    handlers: dict[str, Handler] = {
        "file": file_job,
        "refresh": refresh_job,
        "edit_refile": edit_refile_job,
        "hard_delete": hard_delete_job,
    }
    for extra in services.extras.get("handler_factories", []):
        handlers.update(extra(services))
    return handlers


ONE_DAY = timedelta(days=1)
