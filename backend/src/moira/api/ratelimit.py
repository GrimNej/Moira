"""In-process rate limits (App. B). Exceeded: 429 with Retry-After. One process, so memory works."""

from collections import deque
from dataclasses import dataclass, field

from moira.clock import Clock
from moira.errors import MoiraError


class RateLimited(MoiraError):
    code = "rate_limited"
    status = 429

    def __init__(self, retry_after_s: int) -> None:
        super().__init__("Too many requests. Try again in a moment.")
        self.retry_after_s = retry_after_s


@dataclass
class Limiter:
    clock: Clock
    _hits: dict[tuple[str, str], deque[int]] = field(default_factory=dict)

    def check(self, name: str, key: str, limit: int, window_s: int) -> None:
        now = self.clock.now_ms()
        window_ms = window_s * 1000
        hits = self._hits.setdefault((name, key), deque())
        while hits and hits[0] <= now - window_ms:
            hits.popleft()
        if len(hits) >= limit:
            retry = max(1, (hits[0] + window_ms - now + 999) // 1000)
            raise RateLimited(int(retry))
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()
