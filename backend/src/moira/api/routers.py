"""Every API router beyond health, auth and me. Later tasks append theirs here."""

from fastapi import APIRouter


def all_routers() -> list[APIRouter]:
    from moira.api import (
        routes_admin,
        routes_ask,
        routes_hubs,
        routes_nuggets,
        routes_search,
        routes_share,
        routes_sky,
    )

    return [
        routes_ask.router,
        routes_sky.router,
        routes_nuggets.router,
        routes_hubs.router,
        routes_search.router,
        routes_admin.router,
        routes_share.router,
    ]
