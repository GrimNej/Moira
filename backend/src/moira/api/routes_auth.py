"""Sign-in routes (App. B auth rows, §10.2)."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from moira.api import auth
from moira.api.deps import ServicesDep, UserDep, csrf, rate, token_from
from moira.api.schemas import UserOut, user_out
from moira.db.repos import users as repo

router = APIRouter(prefix="/api/auth", dependencies=[Depends(csrf)])


class LinkIn(BaseModel):
    token: str


class TelegramIn(BaseModel):
    init_data: str


class TelegramOut(BaseModel):
    bearer: str
    user: UserOut


def set_cookie(response: Response, token: str, max_age_s: int) -> None:
    response.set_cookie(
        auth.COOKIE, token, max_age=max_age_s, httponly=True, secure=True, samesite="lax", path="/"
    )


@router.post(
    "/link",
    status_code=204,
    response_class=Response,
    dependencies=[Depends(rate("auth_link", 5, 60, by="ip"))],
)
async def link(body: LinkIn, services: ServicesDep, response: Response) -> Response:
    user = auth.consume_login_token(services, body.token)
    token = auth.start_session(services, user, "login_link")
    response.status_code = 204
    set_cookie(response, token, auth.session_lifetime_ms(services, user) // 1000)
    return response


@router.post("/telegram", dependencies=[Depends(rate("auth_tg", 10, 60, by="ip"))])
async def telegram(body: TelegramIn, services: ServicesDep) -> TelegramOut:
    user = auth.telegram_user(services, body.init_data, services.clock)
    token = auth.start_session(services, user, "mini_app")
    return TelegramOut(bearer=token, user=user_out(services, user))


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request, user: UserDep, services: ServicesDep) -> Response:
    token = token_from(request)
    if token:
        repo.delete_session(services.system, auth.hash_token(token))
    response = Response(status_code=204)
    response.delete_cookie(auth.COOKIE, path="/")
    return response


@router.post("/logout-others", status_code=204, response_class=Response)
async def logout_others(request: Request, user: UserDep, services: ServicesDep) -> Response:
    token = token_from(request) or ""
    repo.delete_other_sessions(services.system, user.id, auth.hash_token(token))
    return Response(status_code=204)
