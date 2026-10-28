"""GET /api/sky (§7.7.4) and GET /api/events (live updates over SSE)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from moira import sky
from moira.api.deps import ServicesDep, UserDep, csrf, rate
from moira.api.ratelimit import RateLimited
from moira.api.sse import HEADERS, frame

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])
MAX_STREAMS = 5
PING_S = 25.0


@router.get("/sky", dependencies=[Depends(rate("sky", 60, 60))])
async def get_sky(
    user: UserDep, services: ServicesDep, since: str | None = Query(default=None)
) -> dict[str, Any]:
    conn = services.memories.open(user.memory_path)
    cursor = int(since) if since and since.isdigit() else None
    return sky.payload(conn, now_ms=services.clock.now_ms(), since=cursor)


@router.get("/events")
async def get_events(user: UserDep, services: ServicesDep) -> StreamingResponse:
    bus = services.extras["bus"]
    if bus.count(user.id) >= MAX_STREAMS:
        raise RateLimited(30)
    queue = bus.subscribe(user.id)

    async def body() -> AsyncIterator[str]:
        try:
            yield frame("ping", {})
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=PING_S)
                except TimeoutError:
                    yield frame("ping", {})
                    continue
                yield frame(event, data)
        finally:
            bus.unsubscribe(user.id, queue)

    return StreamingResponse(body(), media_type="text/event-stream", headers=HEADERS)
