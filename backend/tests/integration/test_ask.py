"""T28–T29: answer tier, citation validation (principle 10), deep tier, follow-ups, degraded."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from moira.ai.schemas import AnswerOutput
from moira.capture.service import CaptureInput
from moira.db.repos import events
from moira.errors import AiUnavailable
from moira.search.ask import DEGRADED, NOT_FOUND, AskService
from moira.services import Services
from tests.conftest import World, run_jobs

K = ZoneInfo("Asia/Kathmandu")


async def save(app: Services, world: World, text: str) -> str:
    r = app.capture.capture(CaptureInput(channel="web", text=text), world.owner)
    assert r.nugget is not None
    await run_jobs(app)
    return r.nugget.public_id


async def test_answer_cites_a_real_memory_and_stores_a_turn(app: Services, world: World) -> None:
    pid = await save(app, world, "Josh's email is josh.r@example.com")
    await save(app, world, "buy oat milk")
    seen: list[tuple[str, dict[str, Any]]] = []

    async def emit(event: str, data: dict[str, Any]) -> None:
        seen.append((event, data))

    res = await AskService(app).ask(world.owner, "josh's email?", emit=emit)
    assert res.confidence == "high" and res.citations[0]["id"] == pid
    assert [e for e, _ in seen] == ["clues", "lit", "status", "answer"]
    status = dict(seen)["status"]["text"]
    assert status.startswith("Looking through") and "Thinking" not in status
    turn = events.turn(world.memory(), res.turn_id)
    assert turn is not None and turn["tier"] == "answer" and pid in turn["cited"]


async def test_p10_uncited_answer_becomes_not_found(app: Services, world: World) -> None:
    await save(app, world, "Josh's email is josh.r@example.com")
    app.extras["llm"].queue(
        "answer",
        AnswerOutput.model_validate(
            {
                "answer": "Your dentist is Dr. Made Up.",
                "citations": [{"id": "n_madeupmadeup", "why": "x"}],
                "also_relevant": ["n_alsoinvented"],
                "confidence": "high",
                "needs_more": False,
            }
        ),
    )
    app.extras["llm"].queue(
        "answer",
        AnswerOutput.model_validate(
            {
                "answer": "Still invented.",
                "citations": [{"id": "n_madeupmadeup", "why": "x"}],
                "also_relevant": [],
                "confidence": "high",
                "needs_more": False,
            }
        ),
    )
    res = await AskService(app).ask(world.owner, "who is my dentist?")
    assert res.confidence == "not_found"
    assert res.answer == NOT_FOUND
    assert all(c["id"] != "n_madeupmadeup" for c in res.citations)
    assert "n_alsoinvented" not in res.also


async def test_count_comes_from_sql(app: Services, world: World) -> None:
    world.clock.set(datetime(2025, 12, 1, 12, tzinfo=K))
    await save(app, world, "read the book Dune")
    world.clock.set(datetime(2026, 3, 1, 12, tzinfo=K))
    for title in (
        "read the book Piranesi",
        "read the book Project Hail Mary",
        "read the book Circe",
    ):
        await save(app, world, title)
    world.clock.set(datetime(2026, 10, 26, 21, tzinfo=K))
    res = await AskService(app).ask(world.owner, "how many books did I save this year")
    assert res.count == 3
    assert "3" in res.answer and res.tier == "deep"


async def test_list_returns_items(app: Services, world: World) -> None:
    for t in ("todo: renew passport", "todo: call the bank", "lofi playlist"):
        await save(app, world, t)
    res = await AskService(app).ask(world.owner, "list all my todos")
    assert res.tier == "deep" and res.count is not None and res.count >= 2


async def test_follow_up_before_that(app: Services, world: World) -> None:
    first = await save(app, world, "turn on XMP in the BIOS")
    world.clock.advance(timedelta(minutes=5))
    await save(app, world, "Josh's email is josh.r@example.com")
    svc = AskService(app)
    a = await svc.ask(world.owner, "josh's email?")
    b = await svc.ask(world.owner, "and the one before that?", conversation_id=a.conversation_id)
    assert b.citations and b.citations[0]["id"] == first
    assert b.answer.startswith("Before that, on ")


async def test_degraded_mode_sends_error_with_fallback_ids(app: Services, world: World) -> None:
    await save(app, world, "Josh's email is josh.r@example.com")
    app.extras["llm"].queue("answer", AiUnavailable("open"))
    seen: list[str] = []
    payloads: dict[str, Any] = {}

    async def emit(event: str, data: dict[str, Any]) -> None:
        seen.append(event)
        payloads[event] = data

    res = await AskService(app).ask(world.owner, "josh's email?", emit=emit)
    assert res.degraded and res.answer == DEGRADED
    assert "error" in seen and payloads["error"]["fallback_ids"]
    assert seen[-1] == "answer"


async def test_not_found_lists_closest(app: Services, world: World) -> None:
    await save(app, world, "buy oat milk")
    app.extras["llm"].queue(
        "answer",
        AnswerOutput.model_validate(
            {
                "answer": "no",
                "citations": [],
                "also_relevant": [],
                "confidence": "not_found",
                "needs_more": False,
            }
        ),
    )
    app.extras["llm"].queue(
        "answer",
        AnswerOutput.model_validate(
            {
                "answer": "no",
                "citations": [],
                "also_relevant": [],
                "confidence": "not_found",
                "needs_more": False,
            }
        ),
    )
    res = await AskService(app).ask(world.owner, "oat milk brand?")
    assert res.confidence == "not_found" and res.also
