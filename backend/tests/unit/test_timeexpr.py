"""T12: every row of the Appendix F test table with FixedClock at Mon 26 Oct 2026 21:00 NPT."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from moira.clock import FixedClock, from_ms, to_ms
from moira.search.timeexpr import TimeHint, extract_time, parse_time

TZ = "Asia/Kathmandu"
K = ZoneInfo(TZ)
NOW = FixedClock(datetime(2026, 10, 26, 21, 0, tzinfo=K)).now()


def local(ms: int) -> datetime:
    return from_ms(ms).astimezone(K)


def at(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> int:
    return to_ms(datetime(y, m, d, h, mi, tzinfo=K))


def hint(text: str) -> TimeHint:
    h = parse_time(text, NOW, TZ)
    assert h is not None, text
    return h


def test_two_weeks_ago_with_tilde() -> None:
    h, rest = extract_time("insta link about AI, ~2 weeks ago", NOW, TZ)
    assert h is not None
    assert h.target_ms == at(2026, 10, 12, 21)
    assert h.sigma_days == pytest.approx(6.3)
    assert not h.has_window
    assert h.label == "around 12 Oct"
    assert "weeks" not in rest and "~" not in rest
    assert "AI" in rest


def test_yesterday() -> None:
    h = hint("yesterday")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 10, 25), at(2026, 10, 26))


def test_last_week() -> None:
    h = hint("last week")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 10, 19), at(2026, 10, 26))


def test_last_month() -> None:
    h = hint("last month")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 9, 1), at(2026, 10, 1))


def test_in_march() -> None:
    h = hint("in March")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 3, 1), at(2026, 4, 1))


def test_on_friday() -> None:
    h = hint("on Friday")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 10, 23), at(2026, 10, 24))
    assert h.label == "Fri 23 Oct"


def test_numeric_day_month() -> None:
    h = hint("12/10")
    assert h.window_from_ms == at(2026, 10, 12)


def test_no_future_dates_without_a_year() -> None:
    h = hint("Oct 30")
    assert h.window_from_ms == at(2025, 10, 30)


def test_three_months_ago() -> None:
    h = hint("3 months ago")
    assert local(h.target_ms).date() == date(2026, 7, 27) or local(h.target_ms).date() == date(
        2026, 7, 26
    )
    assert h.sigma_days == pytest.approx(22.83, abs=0.01)


def test_recently() -> None:
    h = hint("recently")
    assert local(h.target_ms).date() == date(2026, 10, 19)
    assert h.window_from_ms == at(2026, 10, 5, 21)
    assert h.window_to_ms == to_ms(NOW)


def test_a_couple_of_days_ago() -> None:
    h = hint("a couple of days ago")
    assert h.target_ms == at(2026, 10, 24, 21)
    assert h.sigma_days == pytest.approx(0.75)


def test_day_before_yesterday() -> None:
    h = hint("the day before yesterday")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 10, 24), at(2026, 10, 25))


def test_between_days_of_a_month() -> None:
    h = hint("between 1 and 10 October")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 10, 1), at(2026, 10, 11))


def test_last_year() -> None:
    h = hint("last year")
    assert (h.window_from_ms, h.window_to_ms) == (at(2025, 1, 1), at(2026, 1, 1))


def test_no_time_in_plain_question() -> None:
    assert parse_time("josh's email", NOW, TZ) is None


def test_fortnight_ago() -> None:
    h = hint("fortnight ago")
    assert h.target_ms == at(2026, 10, 12, 21)
    assert h.sigma_days == pytest.approx(4.2)


# Beyond the table ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "day"),
    [
        ("2026-10-12", (2026, 10, 12)),
        ("12th of October", (2026, 10, 12)),
        ("12 Oct", (2026, 10, 12)),
        ("12/10/2026", (2026, 10, 12)),
        ("last Monday", (2026, 10, 19)),
        ("on sun", (2026, 10, 25)),
    ],
)
def test_specific_days(text: str, day: tuple[int, int, int]) -> None:
    assert hint(text).window_from_ms == at(*day)


def test_modifier_drops_window_and_widens() -> None:
    h = hint("around last week")
    assert not h.has_window
    assert h.sigma_days == pytest.approx(4.5)


def test_this_morning_and_tonight() -> None:
    assert hint("this morning").target_ms == at(2026, 10, 26, 9)
    assert hint("tonight").window_to_ms == at(2026, 10, 27, 2)


def test_before_and_since_are_open_ended() -> None:
    before = hint("before 12 Oct")
    assert before.window_from_ms is None and before.window_to_ms == at(2026, 10, 12)
    since = hint("since 12 Oct")
    assert since.window_from_ms == at(2026, 10, 12) and since.window_to_ms is None


def test_early_october() -> None:
    h = hint("early October")
    assert (h.window_from_ms, h.window_to_ms) == (at(2026, 10, 1), at(2026, 10, 11))


def test_month_year() -> None:
    h = hint("March 2025")
    assert (h.window_from_ms, h.window_to_ms) == (at(2025, 3, 1), at(2025, 4, 1))


def test_may_as_a_verb_is_ignored() -> None:
    assert parse_time("I may have saved a cafe", NOW, TZ) is None


def test_us_zones_read_month_first() -> None:
    h = parse_time("10/12", NOW, "America/New_York")
    assert h is not None
    assert from_ms(h.window_from_ms or 0).astimezone(ZoneInfo("America/New_York")).day == 12


def test_words_are_removed() -> None:
    _, rest = extract_time("that FPS fix from last week please", NOW, TZ)
    assert rest == "that FPS fix from please"
