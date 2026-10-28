"""Human date strings, computed in code in the user's time zone (principle 11, App. N.4).

The AI copies these strings; it never computes a date.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

DAY_MS = 86_400_000


def local(ms: int, tz: str) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=ZoneInfo(tz))


def clock12(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'am' if dt.hour < 12 else 'pm'}"


def full(ms: int, tz: str) -> str:
    """'Mon 12 Oct 2026, 9:40 pm'."""
    dt = local(ms, tz)
    return f"{dt:%a} {dt.day} {dt:%b %Y}, {clock12(dt)}"


def day_month(ms: int, tz: str) -> str:
    """'12 Oct'."""
    dt = local(ms, tz)
    return f"{dt.day} {dt:%b}"


def day_month_year(ms: int, tz: str) -> str:
    """'12 Oct 2026'."""
    dt = local(ms, tz)
    return f"{dt.day} {dt:%b %Y}"


def weekday_date(ms: int, tz: str) -> str:
    """'Mon 12 Oct'."""
    dt = local(ms, tz)
    return f"{dt:%a} {dt.day} {dt:%b}"


def time_only(ms: int, tz: str) -> str:
    return clock12(local(ms, tz))


def relative(ms: int, now_ms: int, tz: str) -> str:
    """'just now', '25 min ago', 'an hour ago', 'Yesterday', '3 days ago', '2 weeks ago'…"""
    diff = now_ms - ms
    if diff < 60_000:
        return "just now"
    minutes = diff // 60_000
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    then, now = local(ms, tz).date(), local(now_ms, tz).date()
    days = (now - then).days
    if days == 0:
        return "an hour ago" if hours == 1 else f"{hours} hours ago"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "a week ago"
    if days < 31:
        return f"{days // 7} weeks ago"
    if days < 60:
        return "a month ago"
    if days < 365:
        return f"{days // 30} months ago"
    return "a year ago" if days < 730 else f"{days // 365} years ago"


def gap(earlier_ms: int, later_ms: int) -> str:
    """'25 min earlier', '3 hours earlier', '2 days earlier'."""
    diff = max(0, later_ms - earlier_ms)
    minutes = diff // 60_000
    if minutes < 1:
        return "moments earlier"
    if minutes < 60:
        return f"{minutes} min earlier"
    hours = minutes // 60
    if hours < 24:
        return "an hour earlier" if hours == 1 else f"{hours} hours earlier"
    days = hours // 24
    return "a day earlier" if days == 1 else f"{days} days earlier"
