"""Prices, pre-flight estimates, budget caps and the usage ledger (§9.5, §9.6)."""

import sqlite3
from dataclasses import dataclass
from datetime import UTC

from moira.clock import Clock
from moira.config import Settings
from moira.db.repos import usage as ledger
from moira.db.repos import users as users_repo
from moira.errors import AiBudgetExceeded
from moira.logging import get_logger

log = get_logger(__name__)

PRICES_AS_OF = "2026-10-26"


@dataclass(frozen=True, slots=True)
class Price:
    input: float  # USD per 1M tokens
    cached: float
    output: float  # includes reasoning


PRICES = {
    "standard": Price(1.25, 0.15, 4.25),
    "contributor": Price(0.10, 0.002, 0.20),
}
WEB_SEARCH_USD = 2.50 / 1000
ASR_USD_PER_HOUR = 0.18
IMAGE_TOKENS = 1500
CHARS_PER_TOKEN = 3.5


def price_for(model: str) -> Price:
    return PRICES["contributor" if model.endswith("contributor") else "standard"]


def estimate_usd(
    model: str, input_chars: int, images: int, max_output_tokens: int, searches: int = 0
) -> float:
    """Pre-flight maximum: uncached input + max output (+ searches)."""
    p = price_for(model)
    tokens_in = input_chars / CHARS_PER_TOKEN + IMAGE_TOKENS * images
    return (tokens_in * p.input + max_output_tokens * p.output) / 1e6 + searches * WEB_SEARCH_USD


def actual_usd(
    model: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    searches: int = 0,
    audio_seconds: int = 0,
) -> float:
    p = price_for(model)
    fresh = max(0, input_tokens - cached_tokens)
    usd = (fresh * p.input + cached_tokens * p.cached + output_tokens * p.output) / 1e6
    return usd + searches * WEB_SEARCH_USD + audio_seconds / 3600 * ASR_USD_PER_HOUR


class Budget:
    """Raises ``AiBudgetExceeded`` before a call that could break a cap. Capture never stops."""

    def __init__(self, system: sqlite3.Connection, settings: Settings, clock: Clock) -> None:
        self.system = system
        self.settings = settings
        self.clock = clock
        self.alerted: set[str] = set()
        self.on_cap_hit: list[object] = []  # callables(name) for the owner alert

    def day(self) -> str:
        return self.clock.now().astimezone(UTC).strftime("%Y-%m-%d")

    def _user_cap(self, user_id: int) -> tuple[str, float] | None:
        user = users_repo.get(self.system, user_id)
        if user is None:
            return None
        s = self.settings
        cap = {
            "owner": s.cap_owner_daily_usd,
            "tester": s.cap_tester_daily_usd,
            "judge": s.cap_judge_daily_usd,
            "sandbox": s.cap_sandbox_daily_usd,
        }[user.kind]
        return f"CAP_{user.kind.upper()}_DAILY_USD", cap

    def check(
        self,
        *,
        user_id: int | None,
        estimate: float,
        searches: int = 0,
        video: bool = False,
    ) -> None:
        s = self.settings
        day = self.day()
        if ledger.spent_total(self.system) + estimate > s.cap_total_usd:
            self._hit("CAP_TOTAL_USD")
            raise AiBudgetExceeded("lifetime cap reached", lifetime=True)
        if ledger.spent_on_day(self.system, day) + estimate > s.cap_global_daily_usd:
            self._hit("CAP_GLOBAL_DAILY_USD")
            raise AiBudgetExceeded("global daily cap reached")
        if user_id is not None:
            cap = self._user_cap(user_id)
            if cap and ledger.spent_on_day(self.system, day, user_id) + estimate > cap[1]:
                self._hit(cap[0])
                raise AiBudgetExceeded(f"{cap[0]} reached")
        if searches and ledger.count_on_day(self.system, day, "web_searches") + searches > (
            s.cap_web_searches_daily
        ):
            self._hit("CAP_WEB_SEARCHES_DAILY")
            raise AiBudgetExceeded("web search cap reached")
        if video and ledger.count_kind_on_day(self.system, day, "video") >= s.cap_video_daily:
            self._hit("CAP_VIDEO_DAILY")
            raise AiBudgetExceeded("video cap reached")

    def _hit(self, name: str) -> None:
        key = f"{self.day()}:{name}"
        if key in self.alerted:
            return
        self.alerted.add(key)
        log.warning("budget_cap_hit", cap=name)
        for callback in self.on_cap_hit:
            try:
                callback(name)  # type: ignore[operator]
            except Exception as exc:  # noqa: BLE001  # an alert must never break a call
                log.error("cap_alert_failed", error=type(exc).__name__)

    def record(self, row: ledger.UsageRow) -> None:
        ledger.insert(self.system, row)
