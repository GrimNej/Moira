"""Filing orchestration (§7.4): context → ENRICH → validate → apply → clean up → notify.

Used by the ``file``, ``refresh`` and ``edit_refile`` jobs. Images are deleted after the
call (principle 2).
"""

from dataclasses import dataclass
from pathlib import Path

from moira.ai import prompts
from moira.ai.client import LLM
from moira.ai.enrich import build_context, enrich, raw_json
from moira.db.repos import nuggets as repo
from moira.db.repos.users import User
from moira.logging import get_logger
from moira.memory.facts import FilingResult, apply_filing
from moira.memory.validate import Mode, validate
from moira.services import Services

log = get_logger(__name__)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


@dataclass
class Filed:
    result: FilingResult
    needs_research: bool
    nugget_public_id: str


def tmp_images(services: Services, user: User, nugget_id: int) -> list[Path]:
    conn = services.memories.open(user.memory_path)
    paths: list[Path] = []
    for raw in repo.raw_events_for(conn, nugget_id):
        meta = raw["media_meta"]
        if not meta:
            continue
        import json

        for f in json.loads(meta).get("tmp_files", []):
            p = Path(f)
            if p.suffix.lower() in IMAGE_SUFFIXES and p.exists():
                paths.append(p)
    return paths[:10]


async def file_nugget(
    services: Services, llm: LLM, user: User, public_id: str, *, mode: Mode = "file"
) -> Filed | None:
    conn = services.memories.open(user.memory_path)
    n = repo.by_public_id(conn, public_id)
    if n is None or n.deleted_at is not None:
        return None
    now = services.clock.now_ms()
    images = tmp_images(services, user, n.id) if mode == "file" else []
    prepare = services.extras.get("prepare_images")
    if prepare is not None and images:
        images = prepare(images)
    note = "This is the user's corrected version." if mode == "edit_refile" else ""
    repo.set_status(conn, n.id, "filing", now)
    ctx = build_context(
        conn, n, now_ms=now, tz=user.tz, embedder=services.embedder, images=images, note=note
    )
    out = await enrich(llm, ctx, user_id=user.id)
    async with services.memories.lock(user.memory_path):
        n = repo.by_public_id(conn, public_id)
        if n is None or n.deleted_at is not None:
            return None
        v = validate(conn, out, ctx, n, mode=mode)
        prompt = prompts.load("enrich")
        group = f"{'file' if mode == 'file' else mode}:{n.public_id}:v{n.version}"
        if mode == "refresh":
            group += f":{now}"
        result = apply_filing(
            conn,
            n,
            v,
            group_id=group,
            model=services.settings.model_main,
            prompt_version=prompt.version,
            raw_output=raw_json(out),
            now=now,
            tz=user.tz,
            embedder=services.embedder,
        )
    for p in images:  # principle 2: media is deleted once read
        p.unlink(missing_ok=True)
    for p in tmp_images(services, user, n.id):
        p.unlink(missing_ok=True)
    log.info(
        "filed",
        user=user.public_id,
        mode=mode,
        fact_changed=result.fact_changed,
        downgrades=len(v.downgrades),
    )
    notify = services.extras.get("notify_filed")
    if notify is not None:
        await notify(user, n.public_id, result)
    return Filed(result, v.needs_research, n.public_id)
