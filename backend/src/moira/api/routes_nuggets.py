"""Memories (App. B): the card, Recent, save, edit, forget, move, unlink, restore, split, undo."""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import BaseModel, Field

from moira import card
from moira.api.deps import ServicesDep, UserDep, csrf, rate
from moira.api.uploads import read_uploads
from moira.capture.service import CaptureInput
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos.nuggets import Nugget
from moira.db.repos.users import User
from moira.errors import NotFound, ValidationFailed
from moira.memory import corrections, forget, importance, undo, versions
from moira.services import Services

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])
KINDS = {
    "links": "link",
    "todos": "todo",
    "people": "person",
    "facts": "fact",
    "ideas": "idea",
    "notes": "note",
}


class SaveIn(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


class SaveOut(BaseModel):
    id: str
    status: str


class EditIn(BaseModel):
    user_text: str = Field(min_length=1, max_length=10_000)


class MoveIn(BaseModel):
    hub_id: str | None = None
    new_hub_name: str | None = None


class UnlinkIn(BaseModel):
    hub_id: str


class SplitIn(BaseModel):
    parts: list[list[int]]


class UndoIn(BaseModel):
    group_id: str | None = None


def _nugget(services: Services, user: User, public_id: str) -> Nugget:
    conn = services.memories.open(user.memory_path)
    n = repo.by_public_id(conn, public_id)
    if n is None or n.deleted_at is not None:
        raise NotFound("That memory is gone.")
    return n


def _publish(services: Services, user: User, event: str, data: dict[str, Any]) -> None:
    bus = services.extras.get("bus")
    if bus is not None:
        bus.publish(user.id, event, data)


@router.get("/nuggets/{public_id}", dependencies=[Depends(rate("card", 120, 60))])
async def get_card(public_id: str, user: UserDep, services: ServicesDep) -> dict[str, Any]:
    conn = services.memories.open(user.memory_path)
    return card.build(conn, public_id, now_ms=services.clock.now_ms(), tz=user.tz)


@router.post(
    "/nuggets/{public_id}/opened",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(rate("opened", 120, 60))],
)
async def opened(public_id: str, user: UserDep, services: ServicesDep) -> Response:
    n = _nugget(services, user, public_id)
    conn = services.memories.open(user.memory_path)
    repo.bump_open_count(conn, n.id)
    importance.recompute(conn, services.clock.now_ms(), [n.id])
    return Response(status_code=204)


@router.get("/recent", dependencies=[Depends(rate("recent", 60, 60))])
async def recent(
    user: UserDep,
    services: ServicesDep,
    cursor: str | None = None,
    kind: str | None = None,
    source: str | None = None,
    hub: str | None = None,
) -> dict[str, Any]:
    conn = services.memories.open(user.memory_path)
    before = None
    if cursor and ":" in cursor:
        t, i = cursor.split(":", 1)
        before = (int(t), int(i))
    hub_id = None
    if hub:
        h = hubs_repo.by_public_id(conn, hub)
        hub_id = h.id if h else -1
    kinds = (KINDS.get(kind, kind),) if kind and kind != "all" else None
    rows = repo.recent(
        conn,
        limit=51,
        before=before,
        sources=(source,) if source else None,
        kinds=kinds,
        hub_id=hub_id,
    )
    items = []
    for n in rows[:50]:
        e = repo.enrichment(conn, n.id)
        prim = hubs_repo.primary_hub(conn, n.id)
        items.append(
            {
                "id": n.public_id,
                "title": card.title_of(conn, n),
                "kind": e["kind"] if e else ("link" if n.url else "note"),
                "source": n.source,
                "hub": {"id": prim.public_id if prim else "", "name": prim.name if prim else ""},
                "t": n.captured_at,
            }
        )
    nxt = f"{rows[49].captured_at}:{rows[49].id}" if len(rows) > 50 else None
    return {"items": items, "next_cursor": nxt}


@router.post("/nuggets", status_code=202, dependencies=[Depends(rate("save", 30, 60))])
async def save(body: SaveIn, user: UserDep, services: ServicesDep) -> SaveOut:
    r = services.capture.capture(CaptureInput(channel="web", text=body.text), user)
    assert r.nugget is not None
    return SaveOut(
        id=r.nugget.public_id, status=r.nugget.status if r.status != "duplicate" else "filed"
    )


@router.post("/nuggets/media", status_code=202, dependencies=[Depends(rate("media", 10, 60))])
async def save_media(
    user: UserDep,
    services: ServicesDep,
    images: list[UploadFile] = File(default=[]),  # noqa: B008
    audio: UploadFile | None = File(default=None),  # noqa: B008
    text: str = Form(default="", max_length=10_000),
) -> SaveOut:
    """Images (up to 10) or one voice note, sniffed by magic bytes (App. B)."""
    media = await read_uploads(services.tmp_dir, images, audio)
    if media.kind == "text" and not text.strip():
        raise ValidationFailed("Nothing to save.")
    r = services.capture.capture(
        CaptureInput(
            channel="web", kind=media.kind, text=text, tmp_files=media.paths, media_meta=media.meta
        ),
        user,
    )
    assert r.nugget is not None
    return SaveOut(id=r.nugget.public_id, status=r.nugget.status)


@router.patch("/nuggets/{public_id}", dependencies=[Depends(rate("edit", 30, 60))])
async def edit(
    public_id: str, body: EditIn, user: UserDep, services: ServicesDep
) -> dict[str, int]:
    n = _nugget(services, user, public_id)
    edited = versions.web_edit(services, user, n, body.user_text)
    if edited is None:
        raise ValidationFailed("This memory cannot be edited.")
    _publish(services, user, "updated", {"id": public_id})
    return {"version": edited.version}


@router.post("/nuggets/{public_id}/forget", dependencies=[Depends(rate("forget", 30, 60))])
async def forget_one(public_id: str, user: UserDep, services: ServicesDep) -> dict[str, Any]:
    n = _nugget(services, user, public_id)
    conn = services.memories.open(user.memory_path)
    done = forget.soft_forget(conn, n, now=services.clock.now_ms())
    services.queue.enqueue(user.id, "hard_delete", ref=n.public_id, delay_ms=forget.UNDO_MS)
    _publish(services, user, "removed", {"id": public_id})
    return {"undo_group_id": done.group_id, "undo_until": done.undo_until}


@router.post("/nuggets/{public_id}/move", dependencies=[Depends(rate("move", 30, 60))])
async def move(
    public_id: str, body: MoveIn, user: UserDep, services: ServicesDep
) -> dict[str, str]:
    n = _nugget(services, user, public_id)
    conn = services.memories.open(user.memory_path)
    group = corrections.move(
        conn,
        n,
        hub_public_id=body.hub_id,
        new_hub_name=body.new_hub_name,
        now=services.clock.now_ms(),
        embedder=services.embedder,
    )
    _publish(services, user, "updated", {"id": public_id})
    return {"group_id": group}


@router.post("/nuggets/{public_id}/unlink", dependencies=[Depends(rate("unlink", 30, 60))])
async def unlink(
    public_id: str, body: UnlinkIn, user: UserDep, services: ServicesDep
) -> dict[str, str]:
    n = _nugget(services, user, public_id)
    conn = services.memories.open(user.memory_path)
    group = corrections.unlink(
        conn, n, hub_public_id=body.hub_id, now=services.clock.now_ms(), embedder=services.embedder
    )
    _publish(services, user, "updated", {"id": public_id})
    return {"group_id": group}


@router.post("/nuggets/{public_id}/restore", dependencies=[Depends(rate("restore", 30, 60))])
async def restore(public_id: str, user: UserDep, services: ServicesDep) -> dict[str, str]:
    n = _nugget(services, user, public_id)
    conn = services.memories.open(user.memory_path)
    group = corrections.restore(conn, n, now=services.clock.now_ms(), embedder=services.embedder)
    _publish(services, user, "updated", {"id": public_id})
    return {"group_id": group}


@router.post("/nuggets/{public_id}/split", dependencies=[Depends(rate("split", 10, 60))])
async def split(
    public_id: str, body: SplitIn, user: UserDep, services: ServicesDep
) -> dict[str, list[str]]:
    n = _nugget(services, user, public_id)
    conn = services.memories.open(user.memory_path)
    created = corrections.split(
        conn, n, body.parts, now=services.clock.now_ms(), embedder=services.embedder
    )
    services.queue.enqueue(user.id, "edit_refile", ref=n.public_id)
    for c in created:
        services.queue.enqueue_file(user.id, c.public_id, c.captured_at)
    return {"ids": [n.public_id, *[c.public_id for c in created]]}


@router.post("/undo", dependencies=[Depends(rate("undo", 30, 60))])
async def undo_route(body: UndoIn, user: UserDep, services: ServicesDep) -> dict[str, str]:
    conn = services.memories.open(user.memory_path)
    now = services.clock.now_ms()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if body.group_id:
            done = body.group_id if undo.undo_group(conn, body.group_id, now=now) else None
        else:
            done = undo.undo_latest(conn, now=now, actors=("ai", "user"))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    if done is None:
        raise NotFound("There is nothing to undo.")
    if done.startswith("forget:"):
        from moira.db.repos import jobs

        jobs.cancel_for_ref(services.system, user.id, done.split(":")[1], now)
    _publish(services, user, "updated", {"group_id": done})
    return {"undone_group_id": done}
