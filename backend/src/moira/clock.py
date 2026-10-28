"""The only place that reads the wall clock (blueprint §13.7, principle 11).

Services take a ``Clock`` so tests can inject ``FixedClock``. Times are stored as
UTC milliseconds since the epoch.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol


def to_ms(dt: datetime) -> int:
    """Convert an aware datetime to UTC milliseconds."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime; attach a time zone first")
    return int(dt.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    """Convert UTC milliseconds to an aware UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time as an aware UTC datetime."""
        ...

    def now_ms(self) -> int:
        """Current time as UTC milliseconds."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def now_ms(self) -> int:
        return to_ms(self.now())


class FixedClock:
    """A clock that only moves when told to."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FixedClock needs an aware datetime")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def now_ms(self) -> int:
        return to_ms(self._now)

    def set(self, when: datetime) -> None:
        if when.tzinfo is None:
            raise ValueError("FixedClock needs an aware datetime")
        self._now = when.astimezone(UTC)

    def advance(self, delta: timedelta) -> None:
        self._now += delta
