"""Every API router beyond health, auth and me. Later tasks append theirs here."""

from fastapi import APIRouter


def all_routers() -> list[APIRouter]:
    from moira.api import routes_ask

    return [routes_ask.router]
