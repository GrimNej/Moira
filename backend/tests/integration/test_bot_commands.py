"""T18: bot commands with a mocked Bot (§4.2.2). Invite codes are stored hashed."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message

from moira import accounts
from moira.bot import handlers_capture, handlers_commands, texts
from moira.db.repos import events, hubs, jobs, nuggets, users
from moira.memory.undo import new_group
from moira.services import Services
from tests.conftest import World


def msg(uid: int = 1000001, text: str = "", mid: int = 1, **extra: Any) -> Message:
    data: dict[str, Any] = {
        "message_id": mid,
        "date": datetime(2026, 10, 26, tzinfo=UTC),
        "chat": {"id": uid, "type": "private"},
        "from": {"id": uid, "is_bot": False, "first_name": "Ana"},
        "text": text,
    }
    data.update(extra)
    return Message.model_validate(data)


def bot() -> MagicMock:
    b = MagicMock()
    b.send_message = AsyncMock()
    b.delete_message = AsyncMock()
    b.set_message_reaction = AsyncMock()
    return b


def cmd(name: str, args: str | None = None) -> CommandObject:
    return CommandObject(prefix="/", command=name, args=args)


def last_text(b: MagicMock) -> str:
    return str(b.send_message.await_args.args[1])


async def test_owner_is_created_on_first_start(services: Services, world: World) -> None:
    world.system.execute("DELETE FROM users")
    b = bot()
    await handlers_commands.cmd_start(msg(), b, services, cmd("start"))
    owner = users.by_telegram_id(world.system, 1000001)
    assert owner is not None and owner.kind == "owner"
    assert last_text(b) == texts.WELCOME_OWNER


async def test_invite_creates_a_tester_and_is_stored_hashed(
    services: Services, world: World
) -> None:
    code = accounts.create_invite(services, "tester", 1, date(2026, 11, 20))
    stored = [r[0] for r in world.system.execute("SELECT code_hash FROM invites")]
    assert code not in stored and accounts.hash_code(code) in stored
    b = bot()
    await handlers_commands.cmd_start(msg(uid=55), b, services, cmd("start", code))
    tester = users.by_telegram_id(world.system, 55)
    assert tester is not None and tester.kind == "tester"
    assert last_text(b) == texts.WELCOME_TESTER
    b2 = bot()
    await handlers_commands.cmd_start(msg(uid=56), b2, services, cmd("start", code))
    assert "doesn't work" in last_text(b2)  # one use only


async def test_judge_invite_expires(services: Services, world: World) -> None:
    code = accounts.create_invite(services, "judge", 50, date(2026, 11, 20))
    await handlers_commands.cmd_start(msg(uid=77), bot(), services, cmd("start", code))
    judge = users.by_telegram_id(world.system, 77)
    assert judge is not None and judge.kind == "judge" and judge.expires_at is not None


async def test_start_without_code_gets_public_link(services: Services) -> None:
    b = bot()
    await handlers_commands.cmd_start(msg(uid=99), b, services, cmd("start"))
    assert "sample memory" in last_text(b)


async def test_help(services: Services) -> None:
    b = bot()
    await handlers_commands.cmd_help(msg(text="/help"), b)
    assert "/web" in last_text(b)


async def test_timezone(services: Services, world: World) -> None:
    b = bot()
    await handlers_commands.cmd_timezone(msg(), b, services, cmd("timezone", "Mars/Base"))
    assert last_text(b) == texts.TIMEZONE_BAD
    await handlers_commands.cmd_timezone(msg(), b, services, cmd("timezone", "Europe/Berlin"))
    assert users.get(world.system, world.owner.id).tz == "Europe/Berlin"  # type: ignore[union-attr]


async def test_forget_last_then_undo_button(services: Services, world: World) -> None:
    b = bot()
    r = await handlers_capture.on_message(msg(text="buy oat milk", mid=10), b, services)
    assert r is not None and r.nugget is not None
    await handlers_commands.cmd_forget(msg(text="/forget", mid=11), b, services)
    conn = world.memory()
    assert nuggets.get(conn, r.nugget.id).deleted_at is not None  # type: ignore[union-attr]
    assert jobs.queued_for_ref(world.system, world.owner.id, r.nugget.public_id, "hard_delete")
    button = b.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][0]
    query = CallbackQuery.model_validate(
        {
            "id": "q",
            "from": {"id": 1000001, "is_bot": False, "first_name": "A"},
            "chat_instance": "c",
            "data": button.callback_data,
        }
    )
    query_answer = AsyncMock()
    object.__setattr__(query, "answer", query_answer)
    await handlers_commands.on_undo_button(query, b, services)
    assert nuggets.get(conn, r.nugget.id).deleted_at is None  # type: ignore[union-attr]
    assert not jobs.queued_for_ref(world.system, world.owner.id, r.nugget.public_id, "hard_delete")


async def test_forget_by_reply_deletes_the_telegram_message(
    services: Services, world: World
) -> None:
    b = bot()
    r = await handlers_capture.on_message(msg(text="old note", mid=20), b, services)
    assert r is not None and r.nugget is not None
    replied = {
        "message_id": 20,
        "date": datetime(2026, 10, 26, tzinfo=UTC),
        "chat": {"id": 1000001, "type": "private"},
        "text": "old note",
    }
    await handlers_commands.cmd_forget(
        msg(text="/forget", mid=21, reply_to_message=replied), b, services
    )
    assert nuggets.get(world.memory(), r.nugget.id).deleted_at is not None  # type: ignore[union-attr]
    b.delete_message.assert_awaited_with(1000001, 20)


async def test_undo_reverts_the_last_ai_group(services: Services, world: World) -> None:
    conn = world.memory()
    hub = hubs.shelves(conn)[0]
    hubs.set_now_line(conn, hub.id, "Now: banana", 1)
    group = new_group("file:n_x:v1")
    events.record(
        conn,
        group_id=group,
        event="now_changed",
        actor="ai",
        now=1,
        hub_id=hub.id,
        before={"now_line": "Now: apple"},
        after={"now_line": "Now: banana"},
    )
    b = bot()
    await handlers_commands.cmd_undo(msg(text="/undo"), b, services)
    assert hubs.get(conn, hub.id).now_line == "Now: apple"  # type: ignore[union-attr]
    assert last_text(b) == texts.UNDONE
    await handlers_commands.cmd_undo(msg(text="/undo"), b, services)
    assert last_text(b) == texts.NOTHING_TO_UNDO


async def test_stats_is_owner_only(services: Services) -> None:
    b = bot()
    await handlers_commands.cmd_stats(msg(), b, services)
    assert "Spent today" in last_text(b)
    b2 = bot()
    await handlers_commands.cmd_stats(msg(uid=55), b2, services)
    b2.send_message.assert_not_awaited()


async def test_export_with_nothing_new_says_so(services: Services) -> None:
    b = bot()
    await handlers_commands.cmd_export(msg(), b, services)
    assert last_text(b) == texts.EXPORT_NOTHING_NEW


async def test_hard_delete_after_ten_minutes(services: Services, world: World) -> None:
    from moira.memory.forget import hard_delete, soft_forget

    r = await handlers_capture.on_message(msg(text="temporary", mid=30), bot(), services)
    assert r is not None and r.nugget is not None
    conn = world.memory()
    soft_forget(conn, r.nugget, now=world.clock.now_ms())
    world.clock.advance(timedelta(minutes=10))
    assert hard_delete(conn, r.nugget.id, now=world.clock.now_ms())
    assert nuggets.get(conn, r.nugget.id) is None
    assert (
        conn.execute("SELECT COUNT(*) FROM nugget_tri WHERE rowid=?", (r.nugget.id,)).fetchone()[0]
        == 0
    )
