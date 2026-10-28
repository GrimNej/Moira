"""App factory and lifespan (blueprint §5.2): one process for the API, the bot and the worker."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from moira.api import routes_auth, routes_health, routes_me
from moira.api.ratelimit import Limiter, RateLimited
from moira.clock import SystemClock
from moira.config import Settings, app_version, load_settings
from moira.errors import MoiraError
from moira.logging import configure_logging, get_logger
from moira.services import Services

log = get_logger(__name__)


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    """Build the app. Tests pass ``services``; production builds them in the lifespan."""
    settings = settings or (services.settings if services else load_settings())
    configure_logging(settings.log_level, json=settings.app_env == "prod")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        background: list[asyncio.Task[None]] = []
        stoppers: list[Callable[[], Awaitable[None]]] = []
        if getattr(app.state, "services", None) is None:
            from moira.app_services import start_background, startup_services

            app.state.services = startup_services(settings)
            background, stoppers = await start_background(app.state.services)
        log.info("startup", env=settings.app_env, version=app_version())
        yield
        for stop in stoppers:
            await stop()
        for task in background:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        log.info("shutdown")

    app = FastAPI(title="Moira", version=app_version(), lifespan=lifespan)
    app.state.settings = settings
    if services is not None:
        app.state.services = services
    app.state.limiter = Limiter(services.clock if services else SystemClock())

    @app.exception_handler(MoiraError)
    async def moira_error(_: Request, exc: MoiraError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimited):
            headers["Retry-After"] = str(exc.retry_after_s)
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}},
            status_code=exc.status,
            headers=headers,
        )

    for module in (routes_health, routes_auth, routes_me):
        app.include_router(module.router)
    from moira.app_services import extra_routers

    for router in extra_routers():
        app.include_router(router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn moira.main:app` builds the app on first access, so importing this module
    # (in tests or tools) never reads the environment.
    if name == "app":
        return create_app()
    raise AttributeError(name)
