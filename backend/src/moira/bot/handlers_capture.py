"""Incoming messages → capture (§4.2.1, App. G). Thin: parse, call the service, react."""

import secrets as pysecrets
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageOriginChannel,
    MessageOriginChat,
    MessageOriginHiddenUser,
    MessageOriginUser,
)

from moira.bot import reactions, texts
from moira.capture.service import CaptureInput, CaptureResult
from moira.clock import to_ms
from moira.logging import get_logger
from moira.services import Services

log = get_logger(__name__)

MAX_DOWNLOAD = 20 * 1024 * 1024
MAX_VIDEO_S = 90
IMAGE_MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def external_id(message: Message) -> str:
    return f"{message.chat.id}:{message.message_id}"


def forward_info(message: Message) -> tuple[int | None, str | None]:
    origin = message.forward_origin
    if origin is None:
        return None, None
    name: str | None
    if isinstance(origin, MessageOriginUser):
        name = origin.sender_user.full_name
    elif isinstance(origin, MessageOriginHiddenUser):
        name = origin.sender_user_name
    elif isinstance(origin, MessageOriginChat):
        name = origin.sender_chat.title
    elif isinstance(origin, MessageOriginChannel):
        name = origin.chat.title
    else:
        name = None
    return to_ms(origin.date), name


async def download(bot: Bot, services: Services, file_id: str, suffix: str) -> str:
    target = Path(services.tmp_dir) / f"{pysecrets.token_hex(12)}{suffix}"
    await bot.download(file_id, destination=target)
    return str(target)


async def to_input(
    message: Message, bot: Bot, services: Services
) -> tuple[CaptureInput | None, str | None]:
    """Build the capture input. Returns (input, reply text if the content is not kept)."""
    text = message.text or message.caption or ""
    posted_at, forward_from = forward_info(message)
    base: dict[str, Any] = {
        "channel": "telegram",
        "text": text,
        "external_id": external_id(message),
        "chat_id": message.chat.id,
        "original_posted_at": posted_at,
        "forward_from": forward_from,
        "media_group_id": message.media_group_id,
    }
    kind = "forward" if message.forward_origin and not (message.photo or message.voice) else "text"

    if message.photo:
        size = max(
            (p for p in message.photo if (p.file_size or 0) <= MAX_DOWNLOAD),
            key=lambda p: p.width * p.height,
            default=None,
        )
        if size is None:
            return None, texts.TEXT_ONLY
        path = await download(bot, services, size.file_id, ".jpg")
        meta = {
            "mime": "image/jpeg",
            "bytes": size.file_size,
            "width": size.width,
            "height": size.height,
        }
        kind = "album" if message.media_group_id else "photo"
        return CaptureInput(kind=kind, tmp_files=[path], media_meta=meta, **base), None

    if message.voice or message.audio:
        media = message.voice or message.audio
        assert media is not None
        if (media.file_size or 0) > MAX_DOWNLOAD:
            return None, texts.TEXT_ONLY
        path = await download(bot, services, media.file_id, ".ogg" if message.voice else ".audio")
        meta = {"mime": media.mime_type, "bytes": media.file_size, "duration_s": media.duration}
        return CaptureInput(kind="voice", tmp_files=[path], media_meta=meta, **base), None

    if message.video or message.video_note:
        clip = message.video or message.video_note
        assert clip is not None
        if (clip.file_size or 0) > MAX_DOWNLOAD or (clip.duration or 0) > MAX_VIDEO_S:
            return CaptureInput(
                kind="video", media_meta={"too_long": True}, **base
            ), texts.CANT_READ_VIDEO
        path = await download(bot, services, clip.file_id, ".mp4")
        meta = {"mime": "video/mp4", "bytes": clip.file_size, "duration_s": clip.duration}
        return CaptureInput(kind="video", tmp_files=[path], media_meta=meta, **base), None

    if message.document:
        doc = message.document
        mime = (doc.mime_type or "").lower()
        name = doc.file_name or "file"
        meta = {"mime": mime, "bytes": doc.file_size, "file_name": name}
        if mime in IMAGE_MIMES and (doc.file_size or 0) <= MAX_DOWNLOAD:
            path = await download(bot, services, doc.file_id, IMAGE_MIMES[mime])
            return CaptureInput(kind="photo", tmp_files=[path], media_meta=meta, **base), None
        if mime in ("image/heic", "image/heif") or name.lower().endswith((".heic", ".heif")):
            return None, texts.HEIC
        if mime == "application/pdf" and (doc.file_size or 0) <= MAX_DOWNLOAD:
            path = await download(bot, services, doc.file_id, ".pdf")
            return CaptureInput(kind="document", tmp_files=[path], media_meta=meta, **base), None
        base["text"] = (text + "\n" if text else "") + f"File: {name}"
        return CaptureInput(kind="document", media_meta=meta, **base), texts.TEXT_ONLY

    if message.location:
        loc = message.location
        base["text"] = f"Location: {loc.latitude:.6f}, {loc.longitude:.6f}"
        return CaptureInput(kind="location", **base), None

    if message.contact:
        c = message.contact
        name = " ".join(p for p in (c.first_name, c.last_name) if p)
        base["text"] = f"Contact: {name} {c.phone_number}".strip()
        return CaptureInput(kind="contact", **base), None

    if message.sticker or message.animation or message.poll or message.dice:
        return None, texts.NOT_KEPT

    if not text:
        return None, None
    return CaptureInput(kind=kind if kind == "forward" else "text", **base), None


async def on_message(message: Message, bot: Bot, services: Services) -> CaptureResult | None:
    """The private-chat message handler (groups are handled in router.py)."""
    if message.from_user is None:
        return None
    user = services.user_by_telegram(message.from_user.id)
    if user is None:
        link = f"{services.settings.public_base_url}/"
        await bot.send_message(message.chat.id, texts.WELCOME_PUBLIC.format(link=link))
        return None

    slow = bool(message.photo or message.voice or message.video or message.document)
    if slow:
        await reactions.react(bot, message.chat.id, message.message_id, reactions.READING)
    inp, reply = await to_input(message, bot, services)
    if inp is None:
        if reply:
            await reactions.react(bot, message.chat.id, message.message_id, reactions.UNSURE)
            await bot.send_message(message.chat.id, reply)
        return None

    result = services.capture.capture(inp, user)
    if result.status == "question":
        ask = services.extras.get("telegram_ask")
        if ask is not None:
            await ask(message, bot, services, user, result)
        return result

    album_follower = result.status == "grouped" and bool(message.media_group_id)
    if reply:
        await reactions.react(bot, message.chat.id, message.message_id, reactions.UNSURE)
        await bot.send_message(message.chat.id, reply)
    elif not album_follower:
        await reactions.react(bot, message.chat.id, message.message_id, reactions.SAVED)
    if result.found_secrets:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.SECRET_DELETE_BUTTON, callback_data=f"del:{message.message_id}"
                    )
                ]
            ]
        )
        await bot.send_message(message.chat.id, texts.SECRET_HIDDEN, reply_markup=keyboard)
    return result


async def on_edited(message: Message, bot: Bot, services: Services) -> None:
    """An edited message is a new version of its raw event and re-files the nugget (§7.10)."""
    if message.from_user is None:
        return
    user = services.user_by_telegram(message.from_user.id)
    if user is None:
        return
    services.capture.edit(
        user,
        "telegram",
        external_id(message),
        message.text or message.caption or "",
        via="telegram_edit",
    )
    # The ✍ reaction comes later, from filing, if the re-file changed a Now line (§7.4.6).


async def on_delete_button(chat_id: int, message_id: int, bot: Bot) -> None:
    """[Delete my message] under the secret warning: allowed within 48 h in private chats."""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as exc:  # noqa: BLE001  # too old or already gone: nothing else to do
        log.info("delete_failed", error=type(exc).__name__)
