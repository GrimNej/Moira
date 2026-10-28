"""T30: SSE events in order; degraded mode sends error with fallback ids; feedback; save-instead."""

import json

import httpx

from moira.api import auth
from moira.capture.service import CaptureInput
from moira.errors import AiUnavailable
from moira.main import create_app
from moira.services import Services
from tests.conftest import World, run_jobs


def client(app: Services, world: World) -> httpx.AsyncClient:
    token = auth.start_session(app, world.owner, "mini_app")
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(services=app)),
        base_url="https://moira.test",
        headers={"Authorization": f"Bearer {token}", "X-Moira": "1"},
    )


def parse_sse(text: str) -> list[tuple[str, dict]]:  # type: ignore[type-arg]
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


async def seed(app: Services, world: World) -> None:
    app.capture.capture(
        CaptureInput(channel="web", text="Josh's email is josh.r@example.com"), world.owner
    )
    await run_jobs(app)


async def test_events_arrive_in_order(app: Services, world: World) -> None:
    await seed(app, world)
    async with client(app, world) as c:
        r = await c.post("/api/ask", json={"question": "josh's email?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-accel-buffering"] == "no"
    events = parse_sse(r.text)
    assert [e for e, _ in events] == ["clues", "lit", "status", "answer", "done"]
    answer = dict(events)["answer"]
    assert answer["confidence"] == "high" and answer["citations"]
    assert answer["tier"] == "answer" and answer["turn_id"] > 0


async def test_breaker_open_sends_error_with_fallback_ids(app: Services, world: World) -> None:
    await seed(app, world)
    app.extras["llm"].queue("answer", AiUnavailable("circuit open"))
    async with client(app, world) as c:
        r = await c.post("/api/ask", json={"question": "josh's email?"})
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert "error" in names and names[-1] == "done"
    error = dict(events)["error"]
    assert error["fallback_ids"] and error["message"].startswith("I can't think it through")


async def test_feedback_and_save_instead(app: Services, world: World) -> None:
    await seed(app, world)
    async with client(app, world) as c:
        r = await c.post("/api/ask", json={"question": "remind me: buy milk?"})
        turn_id = dict(parse_sse(r.text))["answer"]["turn_id"]
        assert (
            await c.post(f"/api/turns/{turn_id}/feedback", json={"value": "found"})
        ).status_code == 204
        saved = await c.post(f"/api/turns/{turn_id}/save-instead")
        assert saved.status_code == 200 and saved.json()["nugget_id"].startswith("n_")
        assert (
            await c.post("/api/turns/99999/feedback", json={"value": "found"})
        ).status_code == 404


async def test_ask_requires_sign_in_and_csrf(app: Services) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(services=app)), base_url="https://moira.test"
    ) as c:
        assert (
            await c.post("/api/ask", json={"question": "x"}, headers={"X-Moira": "1"})
        ).status_code == 401
        assert (await c.post("/api/ask", json={"question": "x"})).status_code == 403
