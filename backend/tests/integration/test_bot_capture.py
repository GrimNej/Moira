"""T16: bot capture handlers with a mocked Bot (§4.2.1, §4.2.3, App. E.4, App. G)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from moira.bot import handlers_capture, reactions, texts
from moira.db.repos import nuggets
from moira.services import Services
from tests.conftest import World

OWNER_TG = 1000001


def msg(mid: int = 1, chat: int = OWNER_TG, ctype: str = "private", **fields: Any) -> Message:
    data: dict[str, Any] = {
        "message_id": mid,
        "date": datetime(2026, 10, 26, 15, 0, tzinfo=UTC),
        "chat": {"id": chat, "type": ctype},
        "from": {"id": OWNER_TG, "is_bot": False, "first_name": "Owner"},
    }
    data.update(fields)
    return Message.model_validate(data)


def fake_bot() -> MagicMock:
    bot = MagicMock()
    bot.set_message_reaction = AsyncMock(return_value=True)
    bot.send_message = AsyncMock()
    bot.leave_chat = AsyncMock()
    bot.delete_message = AsyncMock()

    async def download(file_id: str, destination: Path) -> None:
        if str(destination).endswith((".jpg", ".png", ".webp")):
            from PIL import Image

            Image.new("RGB", (40, 30), "white").save(destination, "JPEG")
        else:
            Path(destination).write_bytes(b"OggS fake voice")

    bot.download = AsyncMock(side_effect=download)
    return bot


def reactions_sent(bot: MagicMock) -> list[str]:
    return [c.kwargs["reaction"][0].emoji for c in bot.set_message_reaction.await_args_list]


async def test_text_is_saved_and_reacted(services: Services, world: World) -> None:
    bot = fake_bot()
    r = await handlers_capture.on_message(msg(text="buy oat milk"), bot, services)
    assert r is not None and r.status == "saved"
    assert reactions_sent(bot) == [reactions.SAVED]
    bot.send_message.assert_not_awaited()  # the bot never sends "Saved!" texts


async def test_link_is_saved_with_source(services: Services) -> None:
    bot = fake_bot()
    r = await handlers_capture.on_message(msg(text="https://youtu.be/Qm8vR2xLk4E"), bot, services)
    assert r is not None and r.nugget is not None and r.nugget.source == "youtube"
    assert reactions_sent(bot) == [reactions.SAVED]


async def test_photo_downloads_largest_and_reacts(services: Services) -> None:
    bot = fake_bot()
    photo = [
        {"file_id": "small", "file_unique_id": "s", "width": 90, "height": 90, "file_size": 1000},
        {"file_id": "big", "file_unique_id": "b", "width": 1280, "height": 960, "file_size": 90000},
    ]
    r = await handlers_capture.on_message(
        msg(photo=photo, caption="router settings"), bot, services
    )
    assert r is not None and r.nugget is not None and r.nugget.source == "screenshot"
    assert bot.download.await_args.args[0] == "big"
    assert reactions_sent(bot) == [reactions.READING, reactions.SAVED]


async def test_album_is_one_nugget_reacted_once(services: Services) -> None:
    bot = fake_bot()
    photo = [{"file_id": "p", "file_unique_id": "p", "width": 10, "height": 10, "file_size": 10}]
    a = await handlers_capture.on_message(msg(1, photo=photo, media_group_id="g1"), bot, services)
    b = await handlers_capture.on_message(msg(2, photo=photo, media_group_id="g1"), bot, services)
    assert a is not None and b is not None and a.nugget and b.nugget
    assert a.nugget.id == b.nugget.id
    assert reactions_sent(bot).count(reactions.SAVED) == 1


async def test_voice_note_enqueues_transcription(services: Services, world: World) -> None:
    bot = fake_bot()
    voice = {
        "file_id": "v",
        "file_unique_id": "v",
        "duration": 4,
        "mime_type": "audio/ogg",
        "file_size": 2000,
    }
    r = await handlers_capture.on_message(msg(voice=voice), bot, services)
    assert r is not None and r.nugget is not None and r.nugget.source == "voice"
    from moira.db.repos import jobs

    assert jobs.queued_for_ref(world.system, world.owner.id, r.nugget.public_id, "transcribe")
    assert reactions_sent(bot)[-1] == reactions.SAVED


async def test_forward_keeps_origin(services: Services) -> None:
    bot = fake_bot()
    origin = {
        "type": "user",
        "date": datetime(2026, 10, 1, tzinfo=UTC),
        "sender_user": {"id": 77, "is_bot": False, "first_name": "Guy"},
    }
    r = await handlers_capture.on_message(
        msg(text="the meeting moved to 4pm", forward_origin=origin), bot, services
    )
    assert r is not None and r.nugget is not None
    assert r.nugget.source == "forward" and r.nugget.forward_from == "Guy"
    assert r.nugget.original_posted_at == int(datetime(2026, 10, 1, tzinfo=UTC).timestamp() * 1000)


async def test_edit_creates_a_version_and_refile_job(services: Services, world: World) -> None:
    bot = fake_bot()
    r = await handlers_capture.on_message(msg(5, text="it was Guy"), bot, services)
    assert r is not None and r.nugget is not None
    await handlers_capture.on_edited(msg(5, text="it was Josh"), bot, services)
    conn = world.memory()
    n = nuggets.get(conn, r.nugget.id)
    assert n is not None and n.user_text == "it was Josh" and n.version == 2
    assert [v["user_text"] for v in nuggets.versions(conn, n.id)] == ["it was Guy"]
    from moira.db.repos import jobs

    assert jobs.queued_for_ref(world.system, world.owner.id, n.public_id, "edit_refile")


async def test_too_long_video_gets_one_line(services: Services) -> None:
    bot = fake_bot()
    video = {
        "file_id": "x",
        "file_unique_id": "x",
        "width": 1,
        "height": 1,
        "duration": 300,
        "file_size": 10,
    }
    await handlers_capture.on_message(msg(video=video), bot, services)
    assert reactions.UNSURE in reactions_sent(bot)
    assert bot.send_message.await_args.args[1] == texts.CANT_READ_VIDEO


async def test_sticker_is_politely_ignored(services: Services) -> None:
    bot = fake_bot()
    sticker = {
        "file_id": "s",
        "file_unique_id": "s",
        "type": "regular",
        "width": 1,
        "height": 1,
        "is_animated": False,
        "is_video": False,
    }
    r = await handlers_capture.on_message(msg(sticker=sticker), bot, services)
    assert r is None
    assert bot.send_message.await_args.args[1] == texts.NOT_KEPT


async def test_secret_gets_the_one_extra_message(services: Services) -> None:
    bot = fake_bot()
    await handlers_capture.on_message(msg(text="wifi password: blue-otter-77"), bot, services)
    assert bot.send_message.await_args.args[1] == texts.SECRET_HIDDEN


async def test_unknown_user_gets_the_public_link(services: Services) -> None:
    bot = fake_bot()
    m = Message.model_validate(
        {
            "message_id": 1,
            "date": datetime(2026, 10, 26, tzinfo=UTC),
            "chat": {"id": 9, "type": "private"},
            "from": {"id": 9, "is_bot": False, "first_name": "Stranger"},
            "text": "hi",
        }
    )
    assert await handlers_capture.on_message(m, bot, services) is None
    assert "sample memory" in bot.send_message.await_args.args[1]


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("josh's email?", "question"),
        ("what was that FPS fix", "question"),
        ("/ask palette from github", "question"),
        ("good reel https://instagram.com/reel/abc?", "saved"),
        ("remind me: buy milk?", "question"),
        ("my favorite fruit is now banana", "saved"),
        ("find a good cafe near thamel", "question"),
    ],
)
async def test_question_or_save_table(services: Services, text: str, status: str) -> None:
    r = await handlers_capture.on_message(msg(text=text), fake_bot(), services)
    assert r is not None and r.status == status


async def test_group_chats_get_one_line_and_the_bot_leaves(services: Services) -> None:
    from moira.bot.router import build_router

    bot = fake_bot()
    router = build_router()
    group_handler = router.message.handlers[0].callback
    await group_handler(msg(chat=-100, ctype="group", text="hi"), bot)
    assert bot.send_message.await_args.args[1] == texts.PRIVATE_ONLY
    bot.leave_chat.assert_awaited_once_with(-100)
