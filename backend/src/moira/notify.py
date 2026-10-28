"""After filing (§7.4.6): a live `filed` event for the web; ✍ in Telegram when a fact changed."""

from typing import Any

from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos.users import User
from moira.logging import get_logger
from moira.memory.facts import FilingResult
from moira.services import Services

log = get_logger(__name__)


async def notify_filed(
    services: Services, user: User, public_id: str, result: FilingResult
) -> None:
    conn = services.memories.open(user.memory_path)
    n = repo.by_public_id(conn, public_id)
    if n is None:
        return
    bus = services.extras.get("bus")
    if bus is not None:
        hub = hubs_repo.get(conn, result.primary_hub_id or 0)
        payload: dict[str, Any] = {
            "id": public_id,
            "hub": hub.public_id if hub else None,
            "hub_name": hub.name if hub else None,
            "fact_changed": result.fact_changed,
            "now": [line for _, line in result.now_changes],
        }
        if result.star is not None:
            payload["x"], payload["y"] = result.star
        bus.publish(user.id, "filed", payload)
        for hid in result.touched_hubs:
            h = hubs_repo.get(conn, hid)
            if h is not None:
                bus.publish(user.id, "hub", {"id": h.public_id, "name": h.name, "now": h.now_line})
    if result.fact_changed:
        bot = services.extras.get("bot")
        raws = [
            r
            for r in repo.raw_events_for(conn, n.id)
            if r["channel"] == "telegram" and r["external_id"] and r["edit_of"] is None
        ]
        if bot is not None and raws:
            from moira.bot.reactions import UPDATED, react

            chat_id, message_id = raws[-1]["external_id"].split(":")
            await react(bot, int(chat_id), int(message_id), UPDATED)


async def tell_user(services: Services, user: User, nugget: Any, what: str) -> None:
    """One short line in Telegram when media could not be read (🤔 + the reason)."""
    from moira.bot import texts
    from moira.bot.reactions import UNSURE, react

    bot = services.extras.get("bot")
    if bot is None:
        return
    conn = services.memories.open(user.memory_path)
    raws = [
        r
        for r in repo.raw_events_for(conn, nugget.id)
        if r["channel"] == "telegram" and r["external_id"]
    ]
    if not raws:
        return
    chat_id, message_id = (int(x) for x in raws[0]["external_id"].split(":"))
    await react(bot, chat_id, message_id, UNSURE)
    message = {"silent_voice": texts.SILENT_VOICE, "video": texts.CANT_READ_VIDEO}.get(
        what, texts.TEXT_ONLY
    )
    await bot.send_message(chat_id, message)
