"""In-process event bus for live updates (§7.4.6, `GET /api/events`). One process, so no broker."""

import asyncio
from collections import defaultdict
from typing import Any


class Bus:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue[tuple[str, dict[str, Any]]]]] = defaultdict(set)

    def subscribe(self, user_id: int) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        q: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=200)
        self._subs[user_id].add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        self._subs[user_id].discard(q)

    def count(self, user_id: int) -> int:
        return len(self._subs[user_id])

    def publish(self, user_id: int, event: str, data: dict[str, Any]) -> None:
        for q in list(self._subs.get(user_id, ())):
            if q.full():
                continue  # a stuck client misses events; it re-syncs with /api/sky?since=
            q.put_nowait((event, data))
