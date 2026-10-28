"""Reactions are the only feedback on save (§4.2.1). One per message; a new one replaces it."""

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ReactionTypeEmoji

from moira.logging import get_logger

log = get_logger(__name__)

SAVED = "👌"
READING = "👀"
UPDATED = "✍"  # ✍️ without the variation selector: the form Telegram's list accepts (J15)
UNSURE = "🤔"


async def react(bot: Bot, chat_id: int, message_id: int, emoji: str) -> bool:
    try:
        await bot.set_message_reaction(
            chat_id=chat_id, message_id=message_id, reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
    except TelegramAPIError as exc:
        log.warning("reaction_failed", error=type(exc).__name__)
        return False
    return True
