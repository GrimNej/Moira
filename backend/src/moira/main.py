"""App factory and lifespan (blueprint §5.2): one process for the API, the bot and the worker.

The bot (T16) and the worker (T13) join the lifespan when they are built.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from moira.api import routes_health
from moira.config import Settings, app_version, load_settings
from moira.errors import MoiraError
from moira.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level, json=settings.app_env == "prod")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("startup", env=settings.app_env, version=app_version(), fake_llm=settings.fake_llm)
        yield
        log.info("shutdown")

    app = FastAPI(title="Moira", version=app_version(), lifespan=lifespan)
    app.state.settings = settings

    @app.exception_handler(MoiraError)
    async def moira_error(_: Request, exc: MoiraError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    app.include_router(routes_health.router)
    return app


def __getattr__(name: str) -> FastAPI:
    # `uvicorn moira.main:app` builds the app on first access, so importing this module
    # (in tests or tools) never reads the environment.
    if name == "app":
        return create_app()
    raise AttributeError(name)
