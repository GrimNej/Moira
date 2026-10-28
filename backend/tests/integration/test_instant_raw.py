"""T15: instant search on raw text through FTS, trigram and exact channels."""

import pytest

from moira.capture.service import CaptureInput
from moira.search.fts import fts_query
from moira.search.instant import raw_search
from tests.conftest import World


def save(world: World, text: str) -> int:
    r = world.capture.capture(CaptureInput(channel="web", text=text), world.owner)
    assert r.nugget is not None
    return r.nugget.id


def ids(world: World, query: str) -> list[int]:
    return [h.nugget_id for h in raw_search(world.memory(), query, "Asia/Kathmandu")]


def test_a_name_finds_the_raw_text(world: World) -> None:
    josh = save(world, "Josh's email is josh.r@example.com")
    save(world, "buy milk")
    assert ids(world, "josh") == [josh]


def test_hex_color_matches_through_trigram(world: World) -> None:
    pal = save(world, "palette for the site: #38bdf8 and #0f172a")
    save(world, "nothing here")
    assert ids(world, "#38BDF8") == [pal]


def test_partial_email_matches_through_trigram(world: World) -> None:
    josh = save(world, "Josh's email is josh.r@example.com")
    assert ids(world, "josh.r@") == [josh]


@pytest.mark.parametrize(
    "query",
    ['josh" OR "', "NEAR(josh milk)", "josh AND NOT milk", "col:josh", "*josh", "(josh", "^josh"],
)
def test_fts_operators_are_neutralised(world: World, query: str) -> None:
    josh = save(world, "Josh's email is josh.r@example.com")
    assert josh in ids(world, query)  # never raises an FTS syntax error


def test_quoted_phrase_uses_substring(world: World) -> None:
    fix = save(world, "FPS fix: turn off fullscreen optimizations")
    assert fix in ids(world, '"fullscreen optim"')


def test_fts_query_quotes_terms() -> None:
    assert fts_query(['a"b', "c"]) == '"a""b" OR "c"*'
    assert fts_query([]) == ""


def test_deleted_nuggets_are_skipped(world: World) -> None:
    josh = save(world, "Josh's email is josh.r@example.com")
    world.memory().execute("UPDATE nuggets SET deleted_at = 1 WHERE id = ?", (josh,))
    assert ids(world, "josh") == []
