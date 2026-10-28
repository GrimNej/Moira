"""The aiogram dispatcher (App. G): private chats only, long polling, commands set at startup."""

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from moira.bot import handlers_capture, texts
from moira.services import Services

ALLOWED_UPDATES = ["message", "edited_message", "callback_query", "my_chat_member"]


def build_router() -> Router:
    router = Router(name="moira")

    @router.message(F.chat.type != ChatType.PRIVATE)
    async def group(message: Message, bot: Bot) -> None:
        await bot.send_message(message.chat.id, texts.PRIVATE_ONLY)
        await bot.leave_chat(message.chat.id)

    # Commands are registered first by handlers_commands.register(router) (T18).
    from moira.bot import handlers_commands

    handlers_commands.register(router)

    @router.message()
    async def any_message(message: Message, bot: Bot, services: Services) -> None:
        await handlers_capture.on_message(message, bot, services)

    @router.edited_message()
    async def edited(message: Message, bot: Bot, services: Services) -> None:
        await handlers_capture.on_edited(message, bot, services)

    @router.callback_query(F.data.startswith("del:"))
    async def delete_secret(query: CallbackQuery, bot: Bot) -> None:
        if query.message is not None and query.data:
            await handlers_capture.on_delete_button(
                query.message.chat.id, int(query.data.split(":", 1)[1]), bot
            )
            await bot.delete_message(query.message.chat.id, query.message.message_id)
        await query.answer()

    return router


def build_dispatcher(services: Services) -> Dispatcher:
    dp = Dispatcher()
    dp["services"] = services
    dp.include_router(build_router())
    return dp


async def on_startup(bot: Bot, services: Services) -> None:
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in texts.COMMANDS])
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text=texts.SKY_BUTTON,
            web_app=WebAppInfo(url=f"{services.settings.public_base_url}/?from=tg"),
        )
    )
