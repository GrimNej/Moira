"""Constellations (App. B): the list, and one hub with members, Now line and history."""

from typing import Any

from fastapi import APIRouter, Depends

from moira import card
from moira.api.deps import ServicesDep, UserDep, csrf, rate
from moira.db.repos import events
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.errors import NotFound

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])


@router.get("/hubs", dependencies=[Depends(rate("hubs", 60, 60))])
async def list_hubs(user: UserDep, services: ServicesDep) -> dict[str, Any]:
    conn = services.memories.open(user.memory_path)
    counts = hubs_repo.counts(conn)
    return {
        "hubs": [
            {
                "id": h.public_id,
                "name": h.name,
                "kind": h.kind,
                "count": counts.get(h.id, 0),
                "now": h.now_line,
            }
            for h in hubs_repo.active(conn)
        ]
    }


@router.get("/hubs/{public_id}", dependencies=[Depends(rate("hubs", 60, 60))])
async def get_hub(public_id: str, user: UserDep, services: ServicesDep) -> dict[str, Any]:
    conn = services.memories.open(user.memory_path)
    hub = hubs_repo.by_public_id(conn, public_id)
    if hub is None:
        raise NotFound("No such constellation.")
    members = []
    for m in hubs_repo.members(conn, hub.id):
        n = repo.get(conn, m.nugget_id)
        if n is not None:
            members.append(
                {
                    "id": n.public_id,
                    "title": card.title_of(conn, n),
                    "role": m.role,
                    "t": n.captured_at,
                    "until": m.until,
                }
            )
    history = [
        {
            "event": r["event"],
            "actor": r["actor"],
            "t": r["created_at"],
            "group_id": r["group_id"],
            "undone": bool(r["undone"]),
        }
        for r in events.for_hub(conn, hub.id)
    ]
    return {
        "id": hub.public_id,
        "name": hub.name,
        "kind": hub.kind,
        "now": hub.now_line,
        "members": members,
        "history": history,
    }
