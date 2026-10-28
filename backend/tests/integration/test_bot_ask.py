"""T31: Telegram answers ≤ 1,200 chars; Show in sky is a web_app button; Save instead saves."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Message

from moira.ai.schemas import AnswerOutput
from moira.bot import handlers_capture, texts
from moira.bot.handlers_ask import on_save_instead
from moira.capture.service import CaptureInput
from moira.db.repos import nuggets
from moira.services import Services
from tests.conftest import World, run_jobs


def msg(text: str, mid: int = 1) -> Message:
    return Message.model_validate(
        {
            "message_id": mid,
            "date": datetime(2026, 10, 26, tzinfo=UTC),
            "chat": {"id": 1000001, "type": "private"},
            "from": {"id": 1000001, "is_bot": False, "first_name": "Owner"},
            "text": text,
        }
    )


def bot() -> MagicMock:
    b = MagicMock()
    for name in (
        "send_message",
        "send_chat_action",
        "set_message_reaction",
        "edit_message_reply_markup",
    ):
        setattr(b, name, AsyncMock())
    return b


async def seed(app: Services, world: World, text: str) -> str:
    r = app.capture.capture(CaptureInput(channel="web", text=text), world.owner)
    await run_jobs(app)
    assert r.nugget is not None
    return r.nugget.public_id


async def test_answer_with_show_in_sky(app: Services, world: World) -> None:
    pid = await seed(app, world, "Josh's email is josh.r@example.com")
    b = bot()
    await handlers_capture.on_message(msg("josh's email?"), b, app)
    b.send_chat_action.assert_awaited()
    call = b.send_message.await_args
    text: str = call.args[1]
    assert len(text) <= 1200 and "Josh" in text
    row = call.kwargs["reply_markup"].inline_keyboard[0]
    assert row[0].text == texts.SHOW_IN_SKY
    assert row[0].web_app.url == f"https://moira.test/?star={pid}&from=tg"
    assert row[1].callback_data.startswith("save:")


async def test_long_answers_are_cut(app: Services, world: World) -> None:
    pid = await seed(app, world, "Josh's email is josh.r@example.com")
    app.extras["llm"].queue(
        "answer",
        AnswerOutput.model_validate(
            {
                "answer": "x" * 5000,
                "citations": [{"id": pid, "why": "y"}],
                "also_relevant": [],
                "confidence": "high",
                "needs_more": False,
            }
        ),
    )
    b = bot()
    await handlers_capture.on_message(msg("josh's email?"), b, app)
    assert len(b.send_message.await_args.args[1]) <= 1200


async def test_not_found_lists_closest(app: Services, world: World) -> None:
    await seed(app, world, "buy oat milk")
    for _ in range(2):
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
    b = bot()
    await handlers_capture.on_message(msg("which oat milk brand?"), b, app)
    text = b.send_message.await_args.args[1]
    assert text.startswith(texts.NOT_FOUND_CLOSEST) and "•" in text


async def test_save_instead_turns_the_question_into_a_nugget(app: Services, world: World) -> None:
    b = bot()
    await handlers_capture.on_message(msg("remind me: buy milk?", mid=7), b, app)
    data = b.send_message.await_args.kwargs["reply_markup"].inline_keyboard[0][-1].callback_data
    query = CallbackQuery.model_validate(
        {
            "id": "q",
            "from": {"id": 1000001, "is_bot": False, "first_name": "A"},
            "chat_instance": "c",
            "data": data,
            "message": {
                "message_id": 8,
                "date": datetime(2026, 10, 26, tzinfo=UTC),
                "chat": {"id": 1000001, "type": "private"},
                "text": "answer",
            },
        }
    )
    answer = AsyncMock()
    object.__setattr__(query, "answer", answer)
    await on_save_instead(query, b, app)
    conn = world.memory()
    raw_id = int(data.split(":")[1])
    raw = nuggets.raw_event(conn, raw_id)
    assert raw is not None and raw["nugget_id"] is not None
    n = nuggets.get(conn, raw["nugget_id"])
    assert n is not None and n.user_text == "remind me: buy milk?"
    answer.assert_awaited_with(texts.SAVED_INSTEAD)
