"""T27: parsing, priors (telescoping, windows), RRF by hand, and full instant retrieval."""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from moira.capture.service import CaptureInput
from moira.search.fuse import rrf
from moira.search.instant import retrieve
from moira.search.parse import parse
from moira.search.priors import history_prior, source_prior, time_prior
from moira.search.timeexpr import TimeHint
from moira.services import Services
from tests.conftest import World, run_jobs

K = ZoneInfo("Asia/Kathmandu")
NOW = datetime(2026, 10, 26, 21, 0, tzinfo=K)
DAY = 86_400_000


def test_parse_the_instagram_question() -> None:
    p = parse("insta link about AI, ~2 weeks ago?", NOW, "Asia/Kathmandu")
    assert p.source == "instagram"
    assert p.time is not None and p.time.label == "around 12 Oct"
    assert p.terms == ["ai"]
    assert p.intent == "lookup"


@pytest.mark.parametrize(
    ("q", "intent", "follow"),
    [
        ("how many books did I save this year", "count", "none"),
        ("all my to-dos", "list", "none"),
        ("and the one before that?", "lookup", "before_that"),
    ],
)
def test_parse_intent(q: str, intent: str, follow: str) -> None:
    p = parse(q, NOW, "Asia/Kathmandu")
    assert p.intent == intent and p.follow_up == follow


def test_parse_exacts_and_phrases() -> None:
    p = parse('josh.r@example.com and "fullscreen optimizations" #38BDF8', NOW, "UTC")
    kinds = {e.kind for e in p.exact}
    assert {"email", "hex_color"} <= kinds
    assert p.phrases == ["fullscreen optimizations"]


def test_telescoping_widens_the_older_side() -> None:
    hint = TimeHint(
        target_ms=100 * DAY, sigma_days=5, window_from_ms=None, window_to_ms=None, label=""
    )
    older = time_prior(100 * DAY - 5 * DAY, hint)
    newer = time_prior(100 * DAY + 5 * DAY, hint)
    assert older == pytest.approx(math.exp(-0.5 * (5 / 8) ** 2))
    assert newer == pytest.approx(math.exp(-0.5))
    assert older > newer
    assert time_prior(0, hint) == 0.04


def test_windows_score_one_inside() -> None:
    hint = TimeHint(
        target_ms=15 * DAY, sigma_days=3, window_from_ms=10 * DAY, window_to_ms=20 * DAY, label=""
    )
    assert time_prior(10 * DAY, hint) == 1.0
    assert time_prior(19 * DAY, hint) == 1.0
    assert time_prior(23 * DAY, hint) == pytest.approx(math.exp(-0.5))
    assert time_prior(10 * DAY - int(3 * 1.6 * DAY), hint) == pytest.approx(math.exp(-0.5))


def test_rrf_matches_a_hand_computed_example() -> None:
    got = rrf({"fts": [1, 2, 3], "exact": [3, 1]}, {"fts": 1.0, "exact": 2.0})
    assert got[1] == pytest.approx(1 / 61 + 2 / 62)
    assert got[2] == pytest.approx(1 / 62)
    assert got[3] == pytest.approx(1 / 63 + 2 / 61)


def test_other_priors() -> None:
    assert source_prior("instagram", "instagram") == 1.7
    assert source_prior("youtube", "instagram") == 0.2
    assert history_prior({"earlier"}, False) == 0.55
    assert history_prior({"earlier"}, True) == 1.2
    assert history_prior({"current"}, False) == 1.0


async def test_vague_question_finds_the_reel(app: Services, world: World) -> None:
    from moira.ai.client import ResearchRaw

    llm = app.extras["llm"]
    llm.queue(
        "research",
        ResearchRaw(
            "CREATOR: @editlab.demo\nTITLE: 5 AI tools\nTOPIC: five AI tools for video editing\n"
            "SUMMARY: five AI tools that cut and caption videos.\nMATCH: exact",
            [{"url": "https://www.instagram.com/reel/C9xYz12AbCd/"}],
            1,
        ),
    )
    world.clock.set(NOW - timedelta(days=14))
    reel = app.capture.capture(
        CaptureInput(channel="web", text="https://www.instagram.com/reel/C9xYz12AbCd/"), world.owner
    )
    await run_jobs(app)
    for i, text in enumerate(
        [
            "AI that turns sketches into UI https://github.com/demo/sketch",
            "buy oat milk",
            "lofi playlist for focus",
        ]
    ):
        world.clock.set(NOW - timedelta(days=3 + i))
        app.capture.capture(CaptureInput(channel="web", text=text), world.owner)
        await run_jobs(app)
    world.clock.set(NOW)
    p = parse("insta link about AI, ~2 weeks ago?", NOW, "Asia/Kathmandu")
    hits = retrieve(world.memory(), p, "Asia/Kathmandu", app.embedder)
    assert reel.nugget is not None
    assert hits and hits[0].nugget_id == reel.nugget.id


async def test_time_only_question(app: Services, world: World) -> None:
    world.clock.set(NOW - timedelta(days=1))
    y = app.capture.capture(CaptureInput(channel="web", text="buy oat milk"), world.owner)
    world.clock.set(NOW - timedelta(days=9))
    app.capture.capture(CaptureInput(channel="web", text="call the bank"), world.owner)
    world.clock.set(NOW)
    p = parse("what did I save yesterday?", NOW, "Asia/Kathmandu")
    hits = retrieve(world.memory(), p, "Asia/Kathmandu", app.embedder)
    assert y.nugget is not None and hits[0].nugget_id == y.nugget.id
