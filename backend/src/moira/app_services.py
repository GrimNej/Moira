"""Wiring: build the services, the job handlers, the bot and the worker for the lifespan.

Each later task registers its routes in ``extra_routers`` and its handlers in
``build_handlers`` so ``main.py`` stays small.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter

from moira.clock import SystemClock
from moira.config import Settings
from moira.embed.model import load_embedder
from moira.jobs.worker import Handler, Worker
from moira.logging import get_logger
from moira.services import Services, build_services

log = get_logger(__name__)


def extra_routers() -> list[APIRouter]:
    """Routers added by later tasks (sky, nuggets, ask, …)."""
    return []


def startup_services(settings: Settings) -> Services:
    clock = SystemClock()
    embedder = load_embedder(
        settings.embed_model,
        settings.embed_dim,
        settings.embed_quantize,
        fake=settings.app_env == "test",
    )
    return build_services(settings, clock, embedder)


def build_handlers(services: Services) -> dict[str, Handler]:
    """Job kind → handler. Filled in as the pipelines are built."""
    return {}


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
            with __import__("contextlib").suppress(Exception):
                await dp.stop_polling()
            await bot.session.close()

        stoppers.append(stop_bot)
    return tasks, stoppers
