"""Export and forget everything (App. B): the user's data leaves with them, or goes away."""

from pathlib import Path

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from moira.api.deps import ServicesDep, UserDep, csrf, rate
from moira.backup.export import build
from moira.db.repos import jobs as jobs_repo
from moira.errors import Forbidden
from moira.services import Services

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])
FORGET_REF = "forget-everything"
GRACE_MS = 24 * 3_600_000


@router.get("/export", dependencies=[Depends(rate("export", 2, 3600))])
async def export(user: UserDep, services: ServicesDep) -> FileResponse:
    if user.kind == "sandbox":
        raise Forbidden("The sample memory can’t be exported.")
    conn = services.memories.open(user.memory_path)
    path = build(conn, Path(services.tmp_dir), user.tz)
    day = services.clock.now().date().isoformat()
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"moira-export-{day}.zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


def _scheduled(services: Services, user_id: int) -> bool:
    return (
        jobs_repo.queued_for_ref(services.system, user_id, FORGET_REF, "forget_everything")
        is not None
    )


@router.post("/forget-everything", dependencies=[Depends(rate("forget_all", 2, 3600))])
async def forget_everything(user: UserDep, services: ServicesDep) -> dict[str, int]:
    if user.kind == "sandbox":
        raise Forbidden("The sample memory deletes itself after 24 hours.")
    now = services.clock.now_ms()
    if not _scheduled(services, user.id):
        services.queue.enqueue(user.id, "forget_everything", ref=FORGET_REF, delay_ms=GRACE_MS)
    job = jobs_repo.queued_for_ref(services.system, user.id, FORGET_REF, "forget_everything")
    return {"scheduled_for": job.run_after if job else now + GRACE_MS}


@router.delete(
    "/forget-everything",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(rate("forget_all_cancel", 2, 3600))],
)
async def cancel_forget_everything(user: UserDep, services: ServicesDep) -> Response:
    with services.system:
        jobs_repo.cancel_for_ref(services.system, user.id, FORGET_REF, services.clock.now_ms())
    return Response(status_code=204)
