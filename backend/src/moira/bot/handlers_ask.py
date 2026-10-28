"""Questions in Telegram (§8.7, §4.2.4): the same answer service as the web, as plain text."""

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Message

from moira.bot import keyboards, texts
from moira.capture.questions import strip_ask
from moira.capture.service import CaptureInput, CaptureResult
from moira.db.repos import nuggets as repo
from moira.db.repos.users import User
from moira.domain import timefmt
from moira.search.ask import DEGRADED, NOT_FOUND, AskService
from moira.services import Services

MAX_CHARS = 1200
SOURCE = {
    "instagram": "Instagram",
    "youtube": "YouTube",
    "github": "GitHub",
    "web": "web",
    "x": "X",
    "tiktok": "TikTok",
    "voice": "voice note",
    "screenshot": "screenshot",
    "typed": "typed",
    "forward": "forward",
}


def row_line(services: Services, user: User, pid: str) -> str:
    conn = services.memories.open(user.memory_path)
    n = repo.by_public_id(conn, pid)
    if n is None:
        return ""
    e = repo.enrichment(conn, n.id)
    title = (e["title"] if e else n.user_text)[:70]
    when = timefmt.day_month(n.captured_at, user.tz)
    return f"• {title} — {when} ({SOURCE.get(n.source, n.source)})"


def format_answer(
    services: Services, user: User, answer: str, confidence: str, closest: list[str], degraded: bool
) -> str:
    if degraded:
        head = DEGRADED
    elif confidence == "not_found":
        head = texts.NOT_FOUND_CLOSEST if closest else texts.NOT_FOUND
    else:
        head = answer
        if confidence == "low" and closest:
            head += "\n\nClose matches:"
    lines = [head]
    if degraded or confidence in ("not_found", "low"):
        lines += [line for pid in closest[:3] if (line := row_line(services, user, pid))]
    text = "\n".join(lines)
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1].rstrip() + "…"


async def telegram_ask(
    message: Message, bot: Bot, services: Services, user: User, captured: CaptureResult
) -> None:
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    conversations: dict[int, str] = services.extras.setdefault("tg_conversations", {})
    question = strip_ask(captured.text)
    if not question:
        await bot.send_message(message.chat.id, texts.HELP)
        return
    res = await AskService(services).ask(
        user, question, conversation_id=conversations.get(message.chat.id)
    )
    conversations[message.chat.id] = res.conversation_id
    if res.confidence == "not_found" and res.answer == NOT_FOUND:
        res.answer = texts.NOT_FOUND
    closest = res.also or res.lit[:3]
    star = res.citations[0]["id"] if res.citations else (closest[0] if closest else None)
    if res.items and res.count:
        lines = [res.answer] + [
            line for pid in res.items[:10] if (line := row_line(services, user, pid))
        ]
        if res.count > 10:
            lines.append(f"and {res.count - 10} more — Show in sky")
        text = "\n".join(lines)[:MAX_CHARS]
    else:
        text = format_answer(services, user, res.answer, res.confidence, closest, res.degraded)
    await bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboards.answer_keyboard(
            services.settings.public_base_url, star, captured.raw_event_id
        ),
    )


async def on_save_instead(query: CallbackQuery, bot: Bot, services: Services) -> None:
    """Turn the question's raw event into a nugget (it was logged raw first)."""
    user = services.user_by_telegram(query.from_user.id)
    raw_id = int((query.data or "save:0").split(":", 1)[1])
    if user is None:
        await query.answer()
        return
    conn = services.memories.open(user.memory_path)
    raw = repo.raw_event(conn, raw_id)
    if raw is None or raw["nugget_id"] is not None:
        await query.answer(texts.SAVED_INSTEAD)
        return
    r = services.capture.capture(
        CaptureInput(channel="telegram", text=strip_ask(raw["text"] or ""), force_save=True), user
    )
    if r.nugget is not None:
        conn.execute("UPDATE raw_events SET nugget_id = ? WHERE id = ?", (r.nugget.id, raw_id))
    await query.answer(texts.SAVED_INSTEAD)
    if query.message is not None:
        await bot.edit_message_reply_markup(
            chat_id=query.message.chat.id, message_id=query.message.message_id, reply_markup=None
        )
