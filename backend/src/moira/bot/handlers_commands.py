"""Bot commands (§4.2.2). Thin: look up the user, call a service, send one short reply."""

import contextlib
from datetime import UTC

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from moira import accounts
from moira.api import auth
from moira.api.routes_me import valid_tz
from moira.bot import texts
from moira.db.repos import jobs as jobs_repo
from moira.db.repos import nuggets as nuggets_repo
from moira.db.repos import usage
from moira.db.repos import users as users_repo
from moira.db.repos.users import User
from moira.memory import forget as forget_mod
from moira.memory import undo as undo_mod
from moira.services import Services

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
DELETE_WINDOW_MS = 48 * 3_600_000


def _user(message: Message, services: Services) -> User | None:
    return services.user_by_telegram(message.from_user.id) if message.from_user else None


async def cmd_start(
    message: Message, bot: Bot, services: Services, command: CommandObject | None = None
) -> None:
    if message.from_user is None:
        return
    name = message.from_user.full_name
    tg_id = message.from_user.id
    link = f"{services.settings.public_base_url}/"
    user = accounts.ensure_owner(services, tg_id, name) or services.user_by_telegram(tg_id)
    code = (command.args or "").strip() if command else ""
    if user is None and code:
        user = accounts.redeem_invite(services, code, tg_id, name)
        if user is None:
            await bot.send_message(message.chat.id, texts.INVALID_INVITE.format(link=link))
            return
    if user is None:
        await bot.send_message(message.chat.id, texts.WELCOME_PUBLIC.format(link=link))
        return
    users_repo.upsert_chat(
        services.system, chat_id=message.chat.id, user_id=user.id, now=services.clock.now_ms()
    )
    welcome = {
        "owner": texts.WELCOME_OWNER,
        "tester": texts.WELCOME_TESTER,
        "judge": texts.WELCOME_JUDGE,
    }.get(user.kind, texts.WELCOME_OWNER)
    await bot.send_message(message.chat.id, welcome)


async def cmd_help(message: Message, bot: Bot) -> None:
    await bot.send_message(message.chat.id, texts.HELP)


async def cmd_web(message: Message, bot: Bot, services: Services) -> None:
    """One-time sign-in button; the token travels in the URL fragment (§10.2)."""
    user = _user(message, services)
    if user is None:
        await bot.send_message(message.chat.id, texts.START_FIRST)
        return
    link = auth.create_login_link(services, user)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.LOGIN_BUTTON, url=link)]]
    )
    await bot.send_message(
        message.chat.id, texts.LOGIN, reply_markup=keyboard, link_preview_options=NO_PREVIEW
    )


async def cmd_timezone(
    message: Message, bot: Bot, services: Services, command: CommandObject | None = None
) -> None:
    user = _user(message, services)
    if user is None:
        await bot.send_message(message.chat.id, texts.START_FIRST)
        return
    tz = (command.args or "").strip() if command else ""
    if not tz:
        await bot.send_message(message.chat.id, texts.TIMEZONE_HELP.format(tz=user.tz))
        return
    if not valid_tz(tz):
        await bot.send_message(message.chat.id, texts.TIMEZONE_BAD)
        return
    users_repo.set_tz(services.system, user.id, tz)
    await bot.send_message(message.chat.id, texts.TIMEZONE_SET.format(tz=tz))


async def cmd_forget(message: Message, bot: Bot, services: Services) -> None:
    """Reply to a saved message to forget it; alone, forgets the most recent nugget."""
    user = _user(message, services)
    if user is None:
        await bot.send_message(message.chat.id, texts.START_FIRST)
        return
    conn = services.memories.open(user.memory_path)
    nugget = None
    original_mid = None
    if message.reply_to_message is not None:
        original_mid = message.reply_to_message.message_id
        raw = nuggets_repo.raw_event_by_external(
            conn, "telegram", f"{message.chat.id}:{original_mid}"
        )
        if raw is not None and raw["nugget_id"]:
            nugget = nuggets_repo.get(conn, raw["nugget_id"])
    else:
        recent = nuggets_repo.recent(conn, limit=1)
        nugget = recent[0] if recent else None
    if nugget is None or nugget.deleted_at is not None:
        await bot.send_message(message.chat.id, texts.NOTHING_TO_UNDO)
        return
    done = forget_mod.soft_forget(conn, nugget, now=services.clock.now_ms())
    services.queue.enqueue(
        user.id, "hard_delete", ref=nugget.public_id, delay_ms=forget_mod.UNDO_MS
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.UNDO, callback_data=f"undo:{done.group_id}"[:64])]
        ]
    )
    await bot.send_message(message.chat.id, texts.FORGOTTEN, reply_markup=keyboard)
    if original_mid is not None and services.clock.now_ms() - nugget.created_at < DELETE_WINDOW_MS:
        # Too old or not allowed: forgetting still worked.
        with contextlib.suppress(Exception):
            await bot.delete_message(message.chat.id, original_mid)


async def cmd_undo(message: Message, bot: Bot, services: Services) -> None:
    """Revert the most recent AI change to your facts (the last hub event group)."""
    user = _user(message, services)
    if user is None:
        await bot.send_message(message.chat.id, texts.START_FIRST)
        return
    conn = services.memories.open(user.memory_path)
    conn.execute("BEGIN IMMEDIATE")
    try:
        group = undo_mod.undo_latest(conn, now=services.clock.now_ms())
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    await bot.send_message(message.chat.id, texts.UNDONE if group else texts.NOTHING_TO_UNDO)


async def on_undo_button(query: CallbackQuery, bot: Bot, services: Services) -> None:
    """The Undo button under "Forgotten." (valid while the hard delete has not run)."""
    user = services.user_by_telegram(query.from_user.id)
    group_id = (query.data or "").split(":", 1)[1] if query.data else ""
    ok = False
    if user is not None and group_id:
        conn = services.memories.open(user.memory_path)
        conn.execute("BEGIN IMMEDIATE")
        try:
            ok = undo_mod.undo_group(conn, group_id, now=services.clock.now_ms())
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        if ok and group_id.startswith("forget:"):
            pid = group_id.split(":")[1]
            jobs_repo.cancel_for_ref(services.system, user.id, pid, services.clock.now_ms())
    await query.answer(texts.UNDONE if ok else texts.NOTHING_TO_UNDO)


async def cmd_stats(message: Message, bot: Bot, services: Services) -> None:
    user = _user(message, services)
    if user is None or user.kind != "owner":
        return
    now = services.clock.now()
    day = now.astimezone(UTC).strftime("%Y-%m-%d")
    conn = services.memories.open(user.memory_path)
    queue = jobs_repo.count_by_status(services.system)
    lines = [
        f"Memories: {nuggets_repo.count_live(conn)}",
        f"Spent today: ${usage.spent_on_day(services.system, day):.2f}"
        f" of ${services.settings.cap_global_daily_usd:.2f}",
        f"Spent in total: ${usage.spent_total(services.system):.2f}"
        f" of ${services.settings.cap_total_usd:.0f}",
        f"Queue: {queue.get('queued', 0)} waiting, {queue.get('running', 0)} running",
        f"Dead jobs: {queue.get('dead', 0)}",
    ]
    await bot.send_message(message.chat.id, "\n".join(lines))


async def cmd_export(message: Message, bot: Bot, services: Services) -> None:
    user = _user(message, services)
    if user is None:
        await bot.send_message(message.chat.id, texts.START_FIRST)
        return
    sender = services.extras.get("telegram_export")
    if sender is not None:
        await sender(message, bot, services, user)
        return
    link = f"{services.settings.public_base_url}/settings"
    await bot.send_message(message.chat.id, texts.EXPORT_LINK.format(link=link))


async def cmd_ask(message: Message, bot: Bot, services: Services) -> None:
    """/ask forces question mode (capture logs it raw first)."""
    from moira.bot import handlers_capture

    await handlers_capture.on_message(message, bot, services)


def register(router: Router) -> None:
    """Attach the command handlers to the router (before the catch-all message handler)."""
    router.message.register(cmd_start, Command("start"))
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_web, Command("web"))
    router.message.register(cmd_timezone, Command("timezone"))
    router.message.register(cmd_forget, Command("forget"))
    router.message.register(cmd_undo, Command("undo"))
    router.message.register(cmd_stats, Command("stats"))
    router.message.register(cmd_export, Command("export"))
    router.message.register(cmd_ask, Command("ask"))
    router.callback_query.register(on_undo_button, F.data.startswith("undo:"))
    from moira.bot.handlers_ask import on_save_instead

    router.callback_query.register(on_save_instead, F.data.startswith("save:"))
