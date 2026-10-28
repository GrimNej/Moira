"""Inline keyboards for answers (§8.7): Show in sky (Mini App) and Save instead."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from moira.bot import texts


def answer_keyboard(base_url: str, star: str | None, raw_event_id: int) -> InlineKeyboardMarkup:
    row = []
    if star:
        row.append(
            InlineKeyboardButton(
                text=texts.SHOW_IN_SKY, web_app=WebAppInfo(url=f"{base_url}/?star={star}&from=tg")
            )
        )
    row.append(InlineKeyboardButton(text=texts.SAVE_INSTEAD, callback_data=f"save:{raw_event_id}"))
    return InlineKeyboardMarkup(inline_keyboard=[row])
