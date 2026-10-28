"""Time grammar (Appendix F): turn "~2 weeks ago" into a TimeHint, in code, never in the AI.

Resolved against the user's local now and time zone. Matched words are removed from the
search terms by the caller (``extract_time`` returns the remaining text).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from moira.clock import to_ms

DAY_MS = 86_400_000
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_ABBR = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
MONTH_NAMES = ("", *(m.capitalize() for m in MONTHS))
MON_RE = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)"
)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WD_RE = (
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)"
)
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "a": 1,
    "an": 1,
    "a couple of": 2,
    "a couple": 2,
    "couple of": 2,
    "a few": 3,
    "few": 3,
    "several": 4,
}
NUM_RE = (
    r"(?:\d+(?:\.\d+)?|a couple of|a couple|couple of|a few|few|several"
    r"|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|an|a)"
)
UNIT_RE = r"(?:days?|d|weeks?|wks?|w|months?|mos?|years?|yrs?|y|fortnights?)"
AGO_RE = r"(?:ago|back|before)"
MOD_RE = r"(?:(?:around|about|approximately|roughly|maybe|like)\s+|~\s*)"


@dataclass(frozen=True, slots=True)
class TimeHint:
    target_ms: int
    sigma_days: float
    window_from_ms: int | None
    window_to_ms: int | None
    label: str

    @property
    def has_window(self) -> bool:
        return self.window_from_ms is not None or self.window_to_ms is not None


@dataclass(frozen=True, slots=True)
class Ctx:
    now: datetime  # aware, in the user's zone
    tz: ZoneInfo
    mdy: bool

    @property
    def today(self) -> date:
        return self.now.date()

    def at(self, d: date, hour: int = 0, minute: int = 0) -> datetime:
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=self.tz)

    def ms(self, d: date, hour: int = 0) -> int:
        return to_ms(self.at(d, hour))


def fmt_day(d: date) -> str:
    return f"{d.day} {MONTH_NAMES[d.month][:3]}"


def fmt_weekday(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()][:3].capitalize()} {fmt_day(d)}"


def month_name(m: int) -> str:
    return MONTH_NAMES[m]


def to_number(word: str) -> float:
    word = word.strip().lower()
    if word in NUMBER_WORDS:
        return NUMBER_WORDS[word]
    return float(word)


def month_of(word: str) -> int:
    w = word.lower()
    return MONTHS.get(w) or MONTH_ABBR[w[:4] if w.startswith("sept") else w[:3]]


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def day_window(c: Ctx, d: date, sigma: float, label: str, hour: int = 12) -> TimeHint:
    return TimeHint(c.ms(d, hour), sigma, c.ms(d), c.ms(d + timedelta(days=1)), label)


def month_window(c: Ctx, year: int, month: int, sigma: float, label: str) -> TimeHint:
    start = date(year, month, 1)
    end = add_months(start, 1)
    middle = c.ms(start) + (c.ms(end) - c.ms(start)) // 2
    return TimeHint(middle, sigma, c.ms(start), c.ms(end), label)


def past_month_year(c: Ctx, month: int) -> int:
    """Most recent past such month (this one if it is that month now)."""
    return c.today.year if month <= c.today.month else c.today.year - 1


def resolve_date(c: Ctx, day: int, month: int, year: int | None) -> date | None:
    try:
        if year is not None:
            return date(year, month, day)
        d = date(c.today.year, month, day)
        return d if d <= c.today else date(c.today.year - 1, month, day)
    except ValueError:
        return None


def numeric_date(c: Ctx, a: int, b: int, year: int | None) -> date | None:
    first = (b, a) if c.mdy else (a, b)  # (day, month)
    for day, month in (first, (first[1], first[0])):
        if 1 <= month <= 12:
            d = resolve_date(c, day, month, year)
            if d is not None:
                return d
    return None


# Rules -------------------------------------------------------------------------------
# Each rule: (regex, builder). Builders return a TimeHint or None (no match after all).

Builder = Callable[[re.Match[str], Ctx], TimeHint | None]
RULES: list[tuple[re.Pattern[str], Builder]] = []


def rule(pattern: str) -> Callable[[Builder], Builder]:
    def deco(fn: Builder) -> Builder:
        RULES.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn

    return deco


def _date_expr(m: re.Match[str], c: Ctx, prefix: str) -> date | None:
    """Resolve the named groups ``<prefix>d/m/y`` or ``<prefix>a/b/y`` of a date match."""
    g = m.groupdict()
    if g.get(prefix + "iso"):
        y, mo, d = (int(x) for x in g[prefix + "iso"].split("-"))
        return resolve_date(c, d, mo, y)
    if g.get(prefix + "num"):
        parts = [int(x) for x in g[prefix + "num"].split("/")]
        year = parts[2] if len(parts) == 3 else None
        if year is not None and year < 100:
            year += 2000
        return numeric_date(c, parts[0], parts[1], year)
    if g.get(prefix + "mon"):
        day = int(g[prefix + "day"])
        year = int(g[prefix + "year"]) if g.get(prefix + "year") else None
        return resolve_date(c, day, month_of(g[prefix + "mon"]), year)
    return None


def date_pattern(p: str) -> str:
    return (
        rf"(?:(?P<{p}iso>\d{{4}}-\d{{1,2}}-\d{{1,2}})"
        rf"|(?P<{p}num>\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?)"
        rf"|(?P<{p}day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<{p}mon>{MON_RE})\b(?:,?\s+(?P<{p}year>\d{{4}}))?"
        rf"|(?P<{p}mon2>{MON_RE})\s+(?P<{p}day2>\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(?P<{p}year2>\d{{4}}))?)"
    )


def _normalize_groups(m: re.Match[str], p: str) -> dict[str, str | None]:
    g = dict(m.groupdict())
    if g.get(p + "mon2"):
        g[p + "mon"], g[p + "day"], g[p + "year"] = g[p + "mon2"], g[p + "day2"], g[p + "year2"]
    return g


class _M:
    """A tiny shim so ``_date_expr`` can read normalized groups."""

    def __init__(self, groups: dict[str, str | None]) -> None:
        self._g = groups

    def groupdict(self) -> dict[str, str | None]:
        return self._g


def any_date(m: re.Match[str], c: Ctx, p: str) -> date | None:
    return _date_expr(_M(_normalize_groups(m, p)), c, p)  # type: ignore[arg-type]


@rule(
    rf"\bbetween\s+(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s+and\s+(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mon>{MON_RE})\b(?:\s+(?P<year>\d{{4}}))?"
)
def _between_days(m: re.Match[str], c: Ctx) -> TimeHint | None:
    month = month_of(m["mon"])
    year = int(m["year"]) if m["year"] else past_month_year(c, month)
    try:
        a, b = date(year, month, int(m["d1"])), date(year, month, int(m["d2"]))
    except ValueError:
        return None
    lo, hi = c.ms(a), c.ms(b + timedelta(days=1))
    return TimeHint(
        (lo + hi) // 2, max(1.0, (hi - lo) / DAY_MS / 2), lo, hi, f"{fmt_day(a)} to {fmt_day(b)}"
    )


@rule(rf"\b(?:between|from)\s+{date_pattern('a')}\s+(?:and|to|until|till)\s+{date_pattern('b')}")
def _between(m: re.Match[str], c: Ctx) -> TimeHint | None:
    a, b = any_date(m, c, "a"), any_date(m, c, "b")
    if a is None or b is None:
        return None
    if b < a:
        a, b = b, a
    lo, hi = c.ms(a), c.ms(b + timedelta(days=1))
    return TimeHint(
        (lo + hi) // 2, max(1.0, (hi - lo) / DAY_MS / 2), lo, hi, f"{fmt_day(a)} to {fmt_day(b)}"
    )


@rule(rf"\b(?P<rel>before|after|since)\s+{date_pattern('a')}")
def _open(m: re.Match[str], c: Ctx) -> TimeHint | None:
    d = any_date(m, c, "a")
    if d is None:
        return None
    rel = m["rel"].lower()
    if rel == "before":
        return TimeHint(c.ms(d), 30.0, None, c.ms(d), f"before {fmt_day(d)}")
    start = c.ms(d + timedelta(days=1)) if rel == "after" else c.ms(d)
    return TimeHint(start, 30.0, start, None, f"{rel} {fmt_day(d)}")


@rule(r"\b(?:the\s+)?day\s+before\s+yesterday\b")
def _day_before_yesterday(m: re.Match[str], c: Ctx) -> TimeHint:
    d = c.today - timedelta(days=2)
    return day_window(c, d, 0.8, fmt_weekday(d))


@rule(r"\byesterday\b")
def _yesterday(m: re.Match[str], c: Ctx) -> TimeHint:
    return day_window(c, c.today - timedelta(days=1), 0.6, "yesterday")


@rule(r"\blast\s+night\b")
def _last_night(m: re.Match[str], c: Ctx) -> TimeHint:
    y = c.today - timedelta(days=1)
    return TimeHint(c.ms(y, 22), 0.4, c.ms(y, 18), c.ms(c.today, 5), "last night")


@rule(r"\b(?:this\s+)?(?P<part>morning|afternoon|evening)\b(?<!\bgood morning)|\btonight\b")
def _part_of_day(m: re.Match[str], c: Ctx) -> TimeHint | None:
    text = m.group(0).lower()
    if not text.startswith(("this", "tonight")):
        return None
    part = "tonight" if "tonight" in text else m["part"].lower()
    target, lo, hi = {
        "morning": (9, 5, 12),
        "afternoon": (15, 12, 17),
        "evening": (19, 17, 21),
        "tonight": (21, 19, 26),
    }[part]
    t = c.today
    return TimeHint(
        c.ms(t, target),
        0.25,
        c.ms(t, lo),
        c.ms(t) + hi * 3_600_000,
        "tonight" if part == "tonight" else f"this {part}",
    )


@rule(r"\btoday\b")
def _today(m: re.Match[str], c: Ctx) -> TimeHint:
    return TimeHint(to_ms(c.now), 0.5, c.ms(c.today), to_ms(c.now), "today")


@rule(r"\bthe\s+other\s+day\b")
def _other_day(m: re.Match[str], c: Ctx) -> TimeHint:
    return TimeHint(to_ms(c.now) - 3 * DAY_MS, 2.0, None, None, "a few days ago")


@rule(rf"\b(?:a\s+)?few\s+days\s+{AGO_RE}\b")
def _few_days(m: re.Match[str], c: Ctx) -> TimeHint:
    return TimeHint(to_ms(c.now) - 3 * DAY_MS, 1.5, None, None, "a few days ago")


@rule(rf"\b(?:(?P<n>{NUM_RE})\s*)?(?P<unit>{UNIT_RE})\s+{AGO_RE}\b")
def _ago(m: re.Match[str], c: Ctx) -> TimeHint | None:
    unit = m["unit"].lower()
    n = to_number(m["n"]) if m["n"] else (1.0 if unit.startswith("fortnight") else 0.0)
    if n <= 0:
        return None
    now = to_ms(c.now)
    if unit.startswith("fortnight"):
        days = 14 * n
        target = now - int(days * DAY_MS)
        return TimeHint(
            target,
            max(2.0, 0.3 * days),
            None,
            None,
            f"around {fmt_day(c.now.date() - timedelta(days=days))}",
        )
    if unit in ("d", "day", "days"):
        days = n
        sigma = max(0.75, 0.3 * n)
    elif unit in ("w", "wk", "wks", "week", "weeks"):
        days = 7 * n
        sigma = max(2.0, 0.3 * days)
    elif unit in ("mo", "mos", "month", "months"):
        days = 30.44 * n
        sigma = max(5.0, 0.25 * days)
    else:
        days = 365.25 * n
        sigma = max(30.0, 0.2 * days)
    target = now - int(days * DAY_MS)
    when = datetime.fromtimestamp(target / 1000, tz=c.tz).date()
    if unit in ("mo", "mos", "month", "months"):
        label = f"around {month_name(when.month)}"
    elif unit in ("y", "yr", "yrs", "year", "years"):
        label = f"around {when.year}"
    else:
        label = f"around {fmt_day(when)}"
    return TimeHint(target, sigma, None, None, label)


@rule(r"\blast\s+week\b")
def _last_week(m: re.Match[str], c: Ctx) -> TimeHint:
    monday = c.today - timedelta(days=c.today.weekday())
    lo, hi = c.ms(monday - timedelta(days=7)), c.ms(monday)
    return TimeHint((lo + hi) // 2, 3.0, lo, hi, "last week")


@rule(r"\bthis\s+week\b")
def _this_week(m: re.Match[str], c: Ctx) -> TimeHint:
    monday = c.today - timedelta(days=c.today.weekday())
    return TimeHint(to_ms(c.now), 3.0, c.ms(monday), to_ms(c.now), "this week")


@rule(r"\blast\s+month\b")
def _last_month(m: re.Match[str], c: Ctx) -> TimeHint:
    start = add_months(c.today.replace(day=1), -1)
    return month_window(c, start.year, start.month, 8.0, month_name(start.month))


@rule(r"\bthis\s+month\b")
def _this_month(m: re.Match[str], c: Ctx) -> TimeHint:
    start = c.today.replace(day=1)
    return TimeHint(to_ms(c.now), 8.0, c.ms(start), to_ms(c.now), "this month")


@rule(r"\b(?P<which>last|this)\s+year\b")
def _year(m: re.Match[str], c: Ctx) -> TimeHint:
    year = c.today.year - (1 if m["which"].lower() == "last" else 0)
    lo, hi = c.ms(date(year, 1, 1)), c.ms(date(year + 1, 1, 1))
    return TimeHint((lo + hi) // 2, 60.0, lo, hi, str(year))


@rule(r"\b(?:recently|lately)\b")
def _recently(m: re.Match[str], c: Ctx) -> TimeHint:
    now = to_ms(c.now)
    return TimeHint(now - 7 * DAY_MS, 7.0, now - 21 * DAY_MS, now, "recently")


@rule(r"\b(?:a\s+while|some\s+time)\s+ago\b")
def _while_ago(m: re.Match[str], c: Ctx) -> TimeHint:
    return TimeHint(to_ms(c.now) - 60 * DAY_MS, 45.0, None, None, "a while ago")


@rule(r"\b(?:long|ages)\s+ago\b")
def _long_ago(m: re.Match[str], c: Ctx) -> TimeHint:
    return TimeHint(to_ms(c.now) - 365 * DAY_MS, 240.0, None, None, "long ago")


@rule(rf"\b(?P<part>early|mid|late)[\s-]+(?P<mon>{MON_RE})\b(?:\s+(?P<year>\d{{4}}))?")
def _part_of_month(m: re.Match[str], c: Ctx) -> TimeHint:
    month = month_of(m["mon"])
    year = int(m["year"]) if m["year"] else past_month_year(c, month)
    first = date(year, month, 1)
    last = add_months(first, 1) - timedelta(days=1)
    lo_day, hi_day = {"early": (1, 10), "mid": (11, 20), "late": (21, last.day)}[m["part"].lower()]
    lo, hi = c.ms(date(year, month, lo_day)), c.ms(date(year, month, hi_day) + timedelta(days=1))
    return TimeHint((lo + hi) // 2, 4.0, lo, hi, f"{m['part'].lower()} {month_name(month)}")


@rule(date_pattern("a"))
def _date(m: re.Match[str], c: Ctx) -> TimeHint | None:
    d = any_date(m, c, "a")
    if d is None:
        return None
    return day_window(c, d, 0.6, fmt_day(d))


@rule(rf"\b(?P<mon>{MON_RE})\s+(?P<year>\d{{4}})\b")
def _month_year(m: re.Match[str], c: Ctx) -> TimeHint:
    month = month_of(m["mon"])
    return month_window(c, int(m["year"]), month, 10.0, f"{month_name(month)} {m['year']}")


@rule(
    rf"\b(?P<pre>in|last|during)\s+(?P<mon>{MON_RE})\b|\b(?P<mon2>january|february|march|april|june|july|august|september|october|november|december)\b"
)
def _month(m: re.Match[str], c: Ctx) -> TimeHint | None:
    word = m["mon"] or m["mon2"]
    if word.lower() == "may" and not m["pre"]:
        return None
    month = month_of(word)
    year = past_month_year(c, month)
    return month_window(c, year, month, 10.0, f"{month_name(month)} {year}")


@rule(rf"\b(?:(?P<pre>on|last)\s+)?(?P<wd>{WD_RE})\b")
def _weekday(m: re.Match[str], c: Ctx) -> TimeHint | None:
    word = m["wd"].lower()
    if not m["pre"] and len(word) <= 3 and word in ("sat", "sun", "wed", "mon"):
        return None  # "sun", "sat" are ordinary words; need "on"/"last" for short forms
    idx = next(i for i, w in enumerate(WEEKDAYS) if w.startswith(word[:3]))
    back = (c.today.weekday() - idx) % 7 or 7  # strictly before today
    d = c.today - timedelta(days=back)
    sigma = 2.0 if (m["pre"] or "").lower() == "last" else 0.6
    return day_window(c, d, sigma, fmt_weekday(d))


MODIFIER = re.compile(rf"{MOD_RE}$", re.IGNORECASE)


def _apply_modifier(h: TimeHint) -> TimeHint:
    target = h.target_ms
    if h.window_from_ms is not None and h.window_to_ms is not None:
        target = (h.window_from_ms + h.window_to_ms) // 2
    label = h.label if h.label.startswith("around") else f"around {h.label}"
    return replace(
        h,
        target_ms=target,
        sigma_days=h.sigma_days * 1.5,
        window_from_ms=None,
        window_to_ms=None,
        label=label,
    )


def extract_time(text: str, now: datetime, tz: str) -> tuple[TimeHint | None, str]:
    """Find the first time expression; return its hint and the text with it removed."""
    zone = ZoneInfo(tz)
    ctx = Ctx(now=now.astimezone(zone), tz=zone, mdy=tz.startswith("America/"))
    best: tuple[int, int, TimeHint] | None = None
    for pattern, build in RULES:
        for m in pattern.finditer(text):
            hint = build(m, ctx)
            if hint is None:
                continue
            if best is None or m.start() < best[0]:
                best = (m.start(), m.end(), hint)
            break
        if best is not None and best[0] == 0:
            break
    if best is None:
        return None, text
    start, end, hint = best
    mod = MODIFIER.search(text[:start])
    if mod:
        hint = _apply_modifier(hint)
        start = mod.start()
    remaining = (text[:start] + " " + text[end:]).strip()
    return hint, re.sub(r"\s{2,}", " ", remaining)


def parse_time(text: str, now: datetime, tz: str) -> TimeHint | None:
    return extract_time(text, now, tz)[0]
