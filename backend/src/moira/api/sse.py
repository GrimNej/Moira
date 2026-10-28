"""Server-sent events (§8.5, N.5): ``event: name\\ndata: json\\n\\n``, never buffered."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi.responses import StreamingResponse

HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


def frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream(work: Callable[[Emit], Awaitable[Any]]) -> StreamingResponse:
    """Run ``work(emit)`` and stream what it emits; ``done`` is always last."""
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put((event, data))

    async def runner() -> None:
        try:
            await work(emit)
        except Exception as exc:  # noqa: BLE001  # the client always gets error + done
            await queue.put(
                (
                    "error",
                    {
                        "message": "Something went wrong. Try again.",
                        "fallback_ids": [],
                        "code": type(exc).__name__,
                    },
                )
            )
        finally:
            await queue.put(None)

    async def body() -> AsyncIterator[str]:
        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield frame(*item)
            yield frame("done", {})
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(body(), media_type="text/event-stream", headers=HEADERS)
