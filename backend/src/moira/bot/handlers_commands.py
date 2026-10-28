"""Bot commands (§4.2.2). Thin: look up the user, call a service, send one short reply."""

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from moira.api import auth
from moira.bot import texts
from moira.services import Services

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def cmd_web(message: Message, bot: Bot, services: Services) -> None:
    """One-time sign-in button; the token travels in the URL fragment (§10.2)."""
    if message.from_user is None:
        return
    user = services.user_by_telegram(message.from_user.id)
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


def register(router: Router) -> None:
    """Attach the command handlers to the router (before the catch-all message handler)."""
    router.message.register(cmd_web, Command("web"))
