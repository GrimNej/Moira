"""T24: research is verified only when a result URL contains the post id; retries; refresh."""

from datetime import timedelta
from unittest.mock import AsyncMock

from moira.ai.client import ResearchRaw
from moira.ai.research import parse, query_text, verify
from moira.capture.service import CaptureInput
from moira.db.repos import hubs, jobs, nuggets
from moira.readers.base import ReaderResult
from moira.services import Services
from tests.conftest import World, run_jobs

REEL = "https://www.instagram.com/reel/C9xYz12AbCd/"
FOUND = (
    "CREATOR: @editlab.demo\nTITLE: 5 AI tools\nTOPIC: five AI tools for video editing\n"
    "SUMMARY: The caption lists five AI tools.\nMATCH: exact"
)


def test_verified_needs_the_post_id_in_a_source() -> None:
    assert verify(REEL, [{"url": "https://www.instagram.com/reel/C9xYz12AbCd/?igsh=x"}])
    assert verify(REEL, [{"url": "https://picuki.example/media/C9xYz12AbCd"}])
    assert not verify(REEL, [{"url": "https://www.instagram.com/reel/OTHER123/"}])
    assert not verify(REEL, [])


def test_query_and_parse() -> None:
    q = query_text(REEL, REEL)
    assert "Post code: C9xYz12AbCd" in q and "The person's note: (none)" in q
    assert parse("CREATOR: unknown\nMATCH: not_found") == {"creator": "", "match": "not_found"}


async def save(app: Services, world: World, text: str) -> nuggets.Nugget:
    r = app.capture.capture(CaptureInput(channel="web", text=text), world.owner)
    assert r.nugget is not None
    return r.nugget


async def test_walled_link_is_researched_before_filing_and_verified(
    app: Services, world: World
) -> None:
    llm = app.extras["llm"]
    llm.queue("research", ResearchRaw(FOUND, [{"url": REEL, "title": "reel"}], 1))
    n = await save(app, world, REEL)
    await run_jobs(app)
    rows = [r for r in nuggets.research_for(world.memory(), n.id) if r["method"] == "web_search"]
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["verified"] == 1
    e = nuggets.enrichment(world.memory(), n.id)
    assert e is not None and "AI tools" in e["title"]  # filing saw the research


async def test_a_different_post_is_only_possible(app: Services, world: World) -> None:
    llm = app.extras["llm"]
    llm.queue("research", ResearchRaw(FOUND, [{"url": "https://www.instagram.com/reel/ZZZ/"}], 2))
    n = await save(app, world, REEL)
    await run_jobs(app)
    row = next(r for r in nuggets.research_for(world.memory(), n.id) if r["method"] == "web_search")
    assert row["verified"] == 0


async def test_not_found_schedules_plus_one_and_plus_seven_days(
    app: Services, world: World
) -> None:
    llm = app.extras["llm"]
    for _ in range(3):
        llm.queue("research", ResearchRaw("MATCH: not_found", [], 1))
    n = await save(app, world, REEL)
    start = world.clock.now_ms()
    await run_jobs(app)
    retry = jobs.queued_for_ref(world.system, world.owner.id, n.public_id, "research_retry")
    assert retry is not None and retry.payload["attempt"] == 2
    assert abs(retry.run_after - start - 86_400_000) < 5 * 60_000
    world.clock.advance(timedelta(days=1))
    await run_jobs(app)
    retry2 = jobs.queued_for_ref(world.system, world.owner.id, n.public_id, "research_retry")
    assert retry2 is not None and retry2.payload["attempt"] == 3
    assert abs(retry2.run_after - world.clock.now_ms() - 7 * 86_400_000) < 5 * 60_000
    world.clock.advance(timedelta(days=7))
    await run_jobs(app)
    assert jobs.queued_for_ref(world.system, world.owner.id, n.public_id, "research_retry") is None
    attempts = [
        r["attempt"]
        for r in nuggets.research_for(world.memory(), n.id)
        if r["method"] == "web_search"
    ]
    assert attempts == [1, 2, 3]


async def test_later_success_refreshes_without_fact_changes(app: Services, world: World) -> None:
    llm = app.extras["llm"]
    await save(app, world, "my favorite fruit is apple")
    await run_jobs(app)
    fruits = next(h for h in hubs.active(world.memory()) if h.name == "Favorite fruits")
    llm.queue("research", ResearchRaw("MATCH: not_found", [], 1))
    n = await save(app, world, REEL)
    await run_jobs(app)
    llm.queue(
        "research",
        ResearchRaw(
            FOUND.replace("five AI tools", "my favorite fruit is now durian"),
            [{"url": REEL}],
            1,
        ),
    )
    world.clock.advance(timedelta(days=1))
    await run_jobs(app)
    assert (
        next(h for h in hubs.active(world.memory()) if h.id == fruits.id).now_line
        == fruits.now_line
    )
    e = nuggets.enrichment(world.memory(), n.id)
    assert e is not None  # refreshed after the late research
    kinds = [k for k, _ in llm.calls]
    assert kinds.count("enrich") >= 3  # apple, the reel, and the refresh


async def test_readable_link_is_read_not_researched(app: Services, world: World) -> None:
    result = ReaderResult(
        "youtube_oembed",
        "ok",
        title="Max FPS setup guide",
        author="TechDemo",
        findings="YouTube video",
        sources=[{"url": "u", "title": "t"}],
    )
    app.extras["read_link"] = AsyncMock(return_value=result)
    n = await save(app, world, "https://youtu.be/Qm8vR2xLk4E")
    await run_jobs(app)
    rows = nuggets.research_for(world.memory(), n.id)
    assert [r["method"] for r in rows] == ["youtube_oembed"]
    assert not any(k == "research" for k, _ in app.extras["llm"].calls)


async def test_same_url_reuses_the_frozen_reading(app: Services, world: World) -> None:
    result = ReaderResult("page_fetch", "ok", title="RAM guide", sources=[])
    mock = AsyncMock(return_value=result)
    app.extras["read_link"] = mock
    await save(app, world, "https://blog.example.com/ram")
    await run_jobs(app)
    n2 = await save(app, world, "https://blog.example.com/ram my notes on this")
    await run_jobs(app)
    assert mock.await_count == 1
    assert nuggets.research_for(world.memory(), n2.id)[0]["title"] == "RAM guide"
