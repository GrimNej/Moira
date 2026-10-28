"""Wiring: build the services, the job handlers, the bot and the worker for the lifespan.

Each later task registers its routes in ``extra_routers`` and its handlers through
``services.extras["handler_factories"]`` so ``main.py`` stays small.
"""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter

from moira.ai.usage import Budget
from moira.bus import Bus
from moira.clock import SystemClock
from moira.config import Settings
from moira.embed.model import load_embedder
from moira.jobs.worker import Handler, Worker
from moira.logging import get_logger
from moira.services import Services, build_services

log = get_logger(__name__)


def extra_routers() -> list[APIRouter]:
    """Routers added by later tasks (sky, nuggets, ask, …)."""
    from moira.api import routers

    return routers.all_routers()


def wire(services: Services, llm: Any = None) -> Services:
    """Attach the AI client, the bus, notifications and the handler factories."""
    from moira.notify import notify_filed

    settings = services.settings
    budget = Budget(services.system, settings, services.clock)
    services.extras["budget"] = budget
    if llm is None:
        if settings.fake_llm:
            from moira.ai.fake import FakeLLM

            llm = FakeLLM()
        else:
            from moira.ai.client import MetaLLM

            llm = MetaLLM(settings, budget, services.clock)
    services.extras["llm"] = llm
    services.extras.setdefault("bus", Bus())
    if "seed_memory" not in services.extras:
        from moira.sandbox.service import install

        install(services)  # judges and sandboxes start from the sample memory (§11.4)

    async def _notify(user: Any, public_id: str, result: Any) -> None:
        await notify_filed(services, user, public_id, result)

    services.extras["notify_filed"] = _notify

    async def _tell(user: Any, nugget: Any, what: str) -> None:
        from moira.notify import tell_user

        await tell_user(services, user, nugget, what)

    services.extras["tell_user"] = _tell
    from moira.bot.handlers_ask import telegram_ask

    services.extras["telegram_ask"] = telegram_ask
    from moira import pipelines

    pipelines.register(services)
    return services


def startup_services(settings: Settings) -> Services:
    clock = SystemClock()
    embedder = load_embedder(
        settings.embed_model,
        settings.embed_dim,
        settings.embed_quantize,
        fake=settings.app_env == "test",
    )
    return wire(build_services(settings, clock, embedder))


def build_handlers(services: Services) -> dict[str, Handler]:
    from moira.jobs import handlers

    return handlers.build(services)


async def start_background(
    services: Services,
) -> tuple[list[asyncio.Task[Any]], list[Callable[[], Awaitable[None]]]]:
    tasks: list[asyncio.Task[Any]] = []
    stoppers: list[Callable[[], Awaitable[None]]] = []
    worker = Worker(
        services.queue, build_handlers(services), concurrency=services.settings.worker_concurrency
    )
    services.extras["worker"] = worker
    tasks.append(asyncio.create_task(worker.run()))
    stoppers.append(worker.stop)
    timers = services.extras.get("timers")
    if timers is not None:
        tasks.append(asyncio.create_task(timers(services)))
    if services.settings.app_env != "test":
        from aiogram import Bot

        from moira.bot.router import ALLOWED_UPDATES, build_dispatcher, on_startup

        bot = Bot(services.settings.telegram_bot_token.get_secret_value())
        dp = build_dispatcher(services)
        services.extras["bot"] = bot

        async def poll() -> None:
            try:
                await on_startup(bot, services)
            except Exception as exc:  # noqa: BLE001  # the API keeps working without the bot
                log.error("bot_startup_failed", error=type(exc).__name__)
            # Do not drop pending updates: messages sent while down must still be saved.
            await dp.start_polling(bot, handle_signals=False, allowed_updates=ALLOWED_UPDATES)

        tasks.append(asyncio.create_task(poll()))

        async def stop_bot() -> None:
            with contextlib.suppress(Exception):
                await dp.stop_polling()
            await bot.session.close()

        stoppers.append(stop_bot)
    return tasks, stoppers
