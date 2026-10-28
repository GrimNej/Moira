"""FastAPI dependencies: services, the signed-in user, CSRF header, rate limits (§10.1–10.3).

Every request resolves session → user → memory. Nothing accepts a memory path or a user id
from the client.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from moira.api import auth
from moira.api.ratelimit import Limiter
from moira.db.repos.users import User
from moira.errors import Forbidden
from moira.services import Services

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def get_limiter(request: Request) -> Limiter:
    limiter: Limiter = request.app.state.limiter
    return limiter


def token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(auth.COOKIE)


def csrf(request: Request) -> None:
    """State-changing requests must send ``X-Moira: 1`` (§10.1)."""
    if request.method not in SAFE_METHODS and request.headers.get("x-moira") != "1":
        raise Forbidden("Missing the X-Moira header.")


def current_user(request: Request, services: Annotated[Services, Depends(get_services)]) -> User:
    user = auth.resolve(services, token_from(request))
    if user is None:
        raise auth.Unauthorized("Sign in first.")
    request.state.user = user
    return user


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate(name: str, limit: int, window_s: int, *, by: str = "user") -> Callable[..., None]:
    """A dependency enforcing ``limit`` requests per ``window_s`` per user (or per IP)."""

    def dep(request: Request, limiter: Annotated[Limiter, Depends(get_limiter)]) -> None:
        if by == "ip":
            key = client_ip(request)
        else:
            user = getattr(request.state, "user", None) or auth.resolve(
                get_services(request), token_from(request)
            )
            key = user.public_id if user is not None else client_ip(request)
        limiter.check(name, key, limit, window_s)

    return dep


ServicesDep = Annotated[Services, Depends(get_services)]
UserDep = Annotated[User, Depends(current_user)]
