"""GET /api/search?q= (App. B): instant results, no AI, with clue labels for the glow."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from moira import card
from moira.api.deps import ServicesDep, UserDep, csrf, rate
from moira.db.repos import nuggets as repo
from moira.search.instant import retrieve
from moira.search.parse import parse

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])
CLUES = {
    "fts": "words",
    "vector": "meaning",
    "exact": "exact match",
    "hubs": "constellation",
    "people": "person",
    "time": "time",
}


@router.get("/search", dependencies=[Depends(rate("search", 60, 60))])
async def search(
    user: UserDep, services: ServicesDep, q: str = Query(min_length=1, max_length=300)
) -> dict[str, Any]:
    conn = services.memories.open(user.memory_path)
    p = parse(q, services.clock.now(), user.tz)
    hits = retrieve(conn, p, user.tz, services.embedder, limit=12)
    results = []
    for h in hits:
        n = repo.get(conn, h.nugget_id)
        if n is None:
            continue
        results.append(
            {
                "id": n.public_id,
                "title": card.title_of(conn, n),
                "t": n.captured_at,
                "source": n.source,
                "clues": [CLUES.get(c, c) for c in h.channels],
            }
        )
    return {"clues": p.clue_dict(), "results": results}
