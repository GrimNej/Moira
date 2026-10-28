"""T34: sky, card, recent, events, hubs, search, corrections and admin over the API."""

from typing import Any

import httpx
import pytest

from moira.api import auth
from moira.db.repos import users
from moira.main import create_app
from moira.services import Services
from tests.conftest import World, run_jobs


def client(app: Services, user: Any) -> httpx.AsyncClient:
    token = auth.start_session(app, user, "mini_app")
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(services=app)),
        base_url="https://moira.test",
        headers={"Authorization": f"Bearer {token}", "X-Moira": "1"},
    )


@pytest.fixture
async def seeded(app: Services, world: World) -> dict[str, str]:
    ids = {}
    async with client(app, world.owner) as c:
        for key, text in [
            ("apple", "my favorite fruit is apple"),
            ("banana", "my favorite fruit is now banana"),
            ("milk", "buy oat milk"),
            ("josh", "Josh's email is josh.r@example.com"),
        ]:
            r = await c.post("/api/nuggets", json={"text": text})
            assert r.status_code == 202
            ids[key] = r.json()["id"]
            await run_jobs(app)
    return ids


async def test_sky_payload_is_columnar(app: Services, world: World, seeded: dict[str, str]) -> None:
    async with client(app, world.owner) as c:
        r = await c.get("/api/sky")
    body = r.json()
    assert body["v"] == 1 and body["cursor"].isdigit()
    stars = body["stars"]
    assert set(stars) == {"id", "x", "y", "kind", "hub", "t", "imp", "flags"}
    assert len({len(v) for v in stars.values()}) == 1 and len(stars["id"]) == 4
    apple = stars["id"].index(seeded["apple"])
    assert stars["flags"][apple] & 1  # earlier
    assert [seeded["apple"], seeded["banana"]] in body["threads"]
    assert any(h["name"] == "Favorite fruits" and h["count"] == 2 for h in body["hubs"])


async def test_sky_since_returns_changes_and_removals(
    app: Services, world: World, seeded: dict[str, str]
) -> None:
    async with client(app, world.owner) as c:
        cursor = (await c.get("/api/sky")).json()["cursor"]
        world.clock.advance(__import__("datetime").timedelta(seconds=5))
        await c.post(f"/api/nuggets/{seeded['milk']}/forget")
        delta = (await c.get(f"/api/sky?since={cursor}")).json()
    assert seeded["milk"] in delta["removed"]


async def test_card_sections(app: Services, world: World, seeded: dict[str, str]) -> None:
    async with client(app, world.owner) as c:
        banana = (await c.get(f"/api/nuggets/{seeded['banana']}")).json()
        apple = (await c.get(f"/api/nuggets/{seeded['apple']}")).json()
        missing = await c.get("/api/nuggets/n_doesnotexist")
    assert banana["now"] == "Favorite fruits: banana." and not banana["isEarlier"]
    assert banana["earlier"][0]["id"] == seeded["apple"]
    assert banana["sent"]["text"] == "my favorite fruit is now banana"
    assert banana["saved"]["local"].startswith("Mon 26 Oct 2026")
    assert apple["isEarlier"] and apple["replacedBy"]["id"] == seeded["banana"]
    assert missing.status_code == 404


async def test_recent_is_paged(app: Services, world: World, seeded: dict[str, str]) -> None:
    async with client(app, world.owner) as c:
        r = (await c.get("/api/recent")).json()
        todos = (await c.get("/api/recent?kind=todos")).json()
    assert next(i["id"] for i in r["items"]) == seeded["josh"]
    assert r["next_cursor"] is None
    assert [i["id"] for i in todos["items"]] == [seeded["milk"]]


async def test_move_unlink_restore_undo(
    app: Services, world: World, seeded: dict[str, str]
) -> None:
    async with client(app, world.owner) as c:
        moved = await c.post(
            f"/api/nuggets/{seeded['milk']}/move", json={"new_hub_name": "Groceries"}
        )
        assert moved.status_code == 200
        card = (await c.get(f"/api/nuggets/{seeded['milk']}")).json()
        assert card["hub"]["name"] == "Groceries"
        assert (
            await c.post("/api/undo", json={"group_id": moved.json()["group_id"]})
        ).status_code == 200
        assert (await c.get(f"/api/nuggets/{seeded['milk']}")).json()["hub"]["name"] != "Groceries"
        restored = await c.post(f"/api/nuggets/{seeded['apple']}/restore")
        assert restored.status_code == 200
        apple = (await c.get(f"/api/nuggets/{seeded['apple']}")).json()
        assert not apple["isEarlier"]
        hub_id = apple["hub"]["id"]
        unlinked = await c.post(
            f"/api/nuggets/{seeded['milk']}/unlink",
            json={"hub_id": (await c.get(f"/api/nuggets/{seeded['milk']}")).json()["hub"]["id"]},
        )
        assert unlinked.status_code in (200, 422)
        assert hub_id


async def test_forget_and_undo(app: Services, world: World, seeded: dict[str, str]) -> None:
    async with client(app, world.owner) as c:
        f = (await c.post(f"/api/nuggets/{seeded['milk']}/forget")).json()
        assert (await c.get(f"/api/nuggets/{seeded['milk']}")).status_code == 404
        await c.post("/api/undo", json={"group_id": f["undo_group_id"]})
        assert (await c.get(f"/api/nuggets/{seeded['milk']}")).status_code == 200


async def test_edit_creates_a_version(app: Services, world: World, seeded: dict[str, str]) -> None:
    async with client(app, world.owner) as c:
        r = await c.patch(f"/api/nuggets/{seeded['milk']}", json={"user_text": "buy almond milk"})
        assert r.json() == {"version": 2}


async def test_search_and_hubs(app: Services, world: World, seeded: dict[str, str]) -> None:
    async with client(app, world.owner) as c:
        s = (await c.get("/api/search?q=josh")).json()
        hubs = (await c.get("/api/hubs")).json()["hubs"]
        fruits = next(h for h in hubs if h["name"] == "Favorite fruits")
        detail = (await c.get(f"/api/hubs/{fruits['id']}")).json()
    assert s["results"][0]["id"] == seeded["josh"]
    assert {m["role"] for m in detail["members"]} == {"current", "earlier"}
    assert detail["history"]


async def test_admin_stats_is_owner_only(
    app: Services, world: World, seeded: dict[str, str]
) -> None:
    tester = users.create(
        world.system,
        public_id="u_testertester",
        kind="tester",
        memory_path="memories/t.db",
        tz="UTC",
        now=1,
    )
    async with client(app, world.owner) as c:
        r = await c.get("/api/admin/stats")
        assert r.status_code == 200 and r.json()["owner_memory"]["nuggets"] == 4
    async with client(app, tester) as c2:
        assert (await c2.get("/api/admin/stats")).status_code == 403


async def test_events_stream_is_capped(app: Services, world: World) -> None:
    bus = app.extras["bus"]
    queues = [bus.subscribe(world.owner.id) for _ in range(5)]
    async with client(app, world.owner) as c:
        r = await c.get("/api/events")
    assert r.status_code == 429
    for q in queues:
        bus.unsubscribe(world.owner.id, q)
