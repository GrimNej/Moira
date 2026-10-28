"""POST /api/sandbox (§11.4): a private, rebased sample memory for 24 hours, no sign-in."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from moira.api import auth
from moira.api.deps import ServicesDep, client_ip, csrf, get_limiter
from moira.api.ratelimit import Limiter
from moira.api.routes_auth import set_cookie
from moira.api.schemas import UserOut, user_out
from moira.sandbox.service import create_sandbox

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])


class SandboxOut(BaseModel):
    user: UserOut


def per_ip(
    request: Request, services: ServicesDep, limiter: Annotated[Limiter, Depends(get_limiter)]
) -> None:
    limit = services.settings.sandbox_create_per_ip_hour
    limiter.check("sandbox", client_ip(request), limit, 3600)


@router.post("/sandbox", status_code=201, dependencies=[Depends(per_ip)])
async def sandbox(services: ServicesDep, response: Response) -> SandboxOut:
    user = create_sandbox(services)
    token = auth.start_session(services, user, "sandbox")
    set_cookie(response, token, auth.session_lifetime_ms(services, user) // 1000)
    return SandboxOut(user=user_out(services, user))
