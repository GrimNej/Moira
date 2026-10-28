"""T17: sign-in by login link and Mini App initData; cookie and bearer; rate limits."""

import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlencode

import httpx
import pytest
from aiogram.types import Message

from moira.api import auth
from moira.bot.handlers_commands import cmd_web
from moira.main import create_app
from moira.services import Services
from tests.conftest import World

H = {"X-Moira": "1"}
TOKEN = "123456:TEST-not-a-real-token"


def client(services: Services) -> httpx.AsyncClient:
    app = create_app(services=services)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://moira.test")


def init_data(user_id: int, auth_date: int, bot_token: str = TOKEN) -> str:
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Owner"}, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def token_of(link: str) -> str:
    assert "#t=" in link and "?" not in link  # the token travels in the fragment
    return link.split("#t=", 1)[1]


async def test_login_link_works_once(services: Services, world: World) -> None:
    link = auth.create_login_link(services, world.owner)
    assert link.startswith("https://moira.test/login#t=")
    async with client(services) as c:
        r = await c.post("/api/auth/link", json={"token": token_of(link)}, headers=H)
        assert r.status_code == 204
        cookie = r.cookies.get(auth.COOKIE)
        assert cookie
        assert "httponly" in r.headers["set-cookie"].lower()
        r2 = await c.post("/api/auth/link", json={"token": token_of(link)}, headers=H)
        assert r2.status_code == 401


async def test_login_link_expires_after_ten_minutes(services: Services, world: World) -> None:
    link = auth.create_login_link(services, world.owner)
    world.clock.advance(timedelta(minutes=10, seconds=1))
    async with client(services) as c:
        r = await c.post("/api/auth/link", json={"token": token_of(link)}, headers=H)
    assert r.status_code == 401


async def test_cookie_and_bearer_both_authenticate_me(services: Services, world: World) -> None:
    async with client(services) as c:
        assert (await c.get("/api/me")).status_code == 401
        link = auth.create_login_link(services, world.owner)
        await c.post("/api/auth/link", json={"token": token_of(link)}, headers=H)
        me = await c.get("/api/me")
        assert me.status_code == 200 and me.json()["id"] == world.owner.public_id
        assert set(me.json()) == {"id", "kind", "display_name", "tz", "caps", "version"}
    bearer = auth.start_session(services, world.owner, "mini_app")
    async with client(services) as c2:
        r = await c2.get("/api/me", headers={"Authorization": f"Bearer {bearer}"})
        assert r.status_code == 200


async def test_mini_app_init_data(services: Services, world: World) -> None:
    now_s = world.clock.now_ms() // 1000
    async with client(services) as c:
        ok = await c.post(
            "/api/auth/telegram", json={"init_data": init_data(1000001, now_s)}, headers=H
        )
        assert ok.status_code == 200 and ok.json()["bearer"]
        forged = await c.post(
            "/api/auth/telegram",
            json={"init_data": init_data(1000001, now_s, bot_token="999:other-bot")},
            headers=H,
        )
        assert forged.status_code == 401
        old = await c.post(
            "/api/auth/telegram",
            json={"init_data": init_data(1000001, now_s - 25 * 3600)},
            headers=H,
        )
        assert old.status_code == 401
        stranger = await c.post(
            "/api/auth/telegram", json={"init_data": init_data(42, now_s)}, headers=H
        )
        assert stranger.status_code == 403


async def test_writes_need_the_csrf_header(services: Services, world: World) -> None:
    link = auth.create_login_link(services, world.owner)
    async with client(services) as c:
        r = await c.post("/api/auth/link", json={"token": token_of(link)})
    assert r.status_code == 403


async def test_rate_limit_returns_429_with_retry_after(services: Services) -> None:
    async with client(services) as c:
        codes = [
            (await c.post("/api/auth/link", json={"token": "x"}, headers=H)).status_code
            for _ in range(6)
        ]
        assert codes[:5] == [401] * 5
        assert codes[5] == 429
        r = await c.post("/api/auth/link", json={"token": "x"}, headers=H)
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


async def test_patch_me_validates_time_zone(services: Services, world: World) -> None:
    bearer = auth.start_session(services, world.owner, "mini_app")
    hdr = {"Authorization": f"Bearer {bearer}", **H}
    async with client(services) as c:
        assert (await c.patch("/api/me", json={"tz": "Mars/Base"}, headers=hdr)).status_code == 422
        r = await c.patch("/api/me", json={"tz": "Europe/London"}, headers=hdr)
        assert r.status_code == 200 and r.json()["tz"] == "Europe/London"


async def test_logout_others(services: Services, world: World) -> None:
    keep = auth.start_session(services, world.owner, "mini_app")
    other = auth.start_session(services, world.owner, "login_link")
    async with client(services) as c:
        r = await c.post(
            "/api/auth/logout-others", headers={"Authorization": f"Bearer {keep}", **H}
        )
        assert r.status_code == 204
        assert (
            await c.get("/api/me", headers={"Authorization": f"Bearer {other}"})
        ).status_code == 401
        assert (
            await c.get("/api/me", headers={"Authorization": f"Bearer {keep}"})
        ).status_code == 200


@pytest.mark.parametrize("known", [True, False])
async def test_web_command_sends_a_fragment_link_without_preview(
    services: Services, known: bool
) -> None:
    from datetime import UTC, datetime

    bot = MagicMock()
    bot.send_message = AsyncMock()
    uid = 1000001 if known else 5
    m = Message.model_validate(
        {
            "message_id": 1,
            "date": datetime(2026, 10, 26, tzinfo=UTC),
            "chat": {"id": uid, "type": "private"},
            "from": {"id": uid, "is_bot": False, "first_name": "A"},
            "text": "/web",
        }
    )
    await cmd_web(m, bot, services)
    kwargs = bot.send_message.await_args.kwargs
    if known:
        url = kwargs["reply_markup"].inline_keyboard[0][0].url
        assert "/login#t=" in url
        assert kwargs["link_preview_options"].is_disabled is True
    else:
        assert "reply_markup" not in kwargs
