"""Pipeline job handlers beyond filing: link reading and research (§7.3, §7.5).

Each task adds its factory to ``register``; ``jobs.handlers.build`` merges them.
"""

import sqlite3
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


def asr_keywords(conn: sqlite3.Connection, now_ms: int) -> list[str]:
    """§7.2.1: up to 50 terms from the user's memory, each ≤ 40 characters."""
    import json
    import re

    from moira.db.repos import hubs as hubs_repo
    from moira.db.repos import people as people_repo

    words: list[str] = []
    for p in people_repo.all_people(conn):
        words += [p.display_name, *p.aliases]
    words += [h.name for h in hubs_repo.active(conn) if h.kind != "shelf"]
    tags: dict[str, int] = {}
    for (raw,) in conn.execute("SELECT tags FROM enrichments").fetchall():
        for t in json.loads(raw):
            tags[t] = tags.get(t, 0) + 1
    words += [t for t, _ in sorted(tags.items(), key=lambda kv: -kv[1])[:20]]
    since = now_ms - 30 * 86_400_000
    for (text,) in conn.execute(
        "SELECT user_text FROM nuggets WHERE captured_at >= ? AND deleted_at IS NULL", (since,)
    ).fetchall():
        words += re.findall(r"(?<![.!?]\s)(?<!^)[A-Z][a-zA-Z]{2,}", text)
    out = [w.strip()[:40] for w in dict.fromkeys(words) if w and w.strip()]
    return out[:50]


def media_handlers(services: Services) -> dict[str, Handler]:
    from pathlib import Path

    from moira.capture import exacts as exacts_mod
    from moira.capture import secrets
    from moira.media.audio import to_wav

    async def transcribe_job(job: Job) -> None:
        user = _user(services, job)
        conn = services.memories.open(user.memory_path)
        n = nuggets_repo.by_public_id(conn, job.ref or "")
        files = [Path(f) for f in job.payload.get("files", [])]
        try:
            if n is None or n.deleted_at is not None:
                return
            llm: LLM = services.extras["llm"]
            keywords = asr_keywords(conn, services.clock.now_ms())
            texts = []
            for f in files:
                if not f.exists():
                    continue
                for wav in to_wav(f):
                    try:
                        t = await llm.transcribe(wav=wav, keywords=keywords, user_id=user.id)
                        texts.append(t.text.strip())
                    finally:
                        wav.unlink(missing_ok=True)  # principle 2
            transcript = " ".join(t for t in texts if t)
            if not transcript:
                silent = services.extras.get("tell_user")
                if silent is not None:
                    await silent(user, n, "silent_voice")
                return
            masked, found = secrets.mask(transcript)
            now = services.clock.now_ms()
            nuggets_repo.set_user_text_from_media(conn, n.id, masked, found, now)
            nuggets_repo.insert_exacts(
                conn,
                n.id,
                [e.as_tuple() for e in exacts_mod.extract(masked, user.tz)],
                "user_text",
            )
            indexing.index_instant(conn, n.id, services.embedder)
        finally:
            for f in files:
                f.unlink(missing_ok=True)

    async def read_video_job(job: Job) -> None:
        """§7.2.3: ffprobe → Files API → VIDEO → content_text; remote and local file deleted."""
        from moira.ai import video as video_ai
        from moira.errors import AiBudgetExceeded, ValidationFailed
        from moira.media import video as video_media

        user = _user(services, job)
        conn = services.memories.open(user.memory_path)
        n = nuggets_repo.by_public_id(conn, job.ref or "")
        files = [Path(f) for f in job.payload.get("files", [])]
        try:
            if n is None or n.deleted_at is not None or not files or not files[0].exists():
                return
            try:
                video_media.check(files[0])
                report = await video_ai.read(services.extras["llm"], files[0], user_id=user.id)
            except ValidationFailed:
                tell = services.extras.get("tell_user")
                if tell is not None:
                    await tell(user, n, "video")
                return
            except AiBudgetExceeded:
                log.info("video_skipped", reason="budget")
                return
            text = report.content_text()
            if not text:
                return
            now = services.clock.now_ms()
            nuggets_repo.append_content_text(conn, n.id, text, now)
            nuggets_repo.insert_research(
                conn, n.id, method="video", status="ok", now=now,
                title=report.topic, author=report.creator, findings=text,
            )  # fmt: skip
            nuggets_repo.insert_exacts(
                conn,
                n.id,
                [e.as_tuple() for e in exacts_mod.extract(text, user.tz)],
                "content_text",
            )
            indexing.index_instant(conn, n.id, services.embedder)
        finally:
            for f in files:
                f.unlink(missing_ok=True)  # principle 2: media is never kept

    return {"transcribe": transcribe_job, "read_video": read_video_job}


def register(services: Services) -> None:
    factories = services.extras.setdefault("handler_factories", [])
    factories.clear()
    factories.append(link_handlers)
    factories.append(media_handlers)
    from moira.jobs import maintenance

    factories.append(maintenance.handlers)
    for extra in services.extras.get("more_factories", []):
        factories.append(extra)
