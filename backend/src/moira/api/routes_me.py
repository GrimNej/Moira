"""GET/PATCH /api/me (App. B)."""

from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from moira.api.deps import ServicesDep, UserDep, csrf
from moira.api.schemas import UserOut, user_out
from moira.db.repos import users as repo
from moira.errors import ValidationFailed

router = APIRouter(prefix="/api", dependencies=[Depends(csrf)])


class MePatch(BaseModel):
    tz: str


def valid_tz(name: str) -> bool:
    if name not in available_timezones():
        return False
    try:
        ZoneInfo(name)
    except (KeyError, ValueError):
        return False
    return True


@router.get("/me")
async def me(user: UserDep, services: ServicesDep) -> UserOut:
    return user_out(services, user)


@router.patch("/me")
async def patch_me(body: MePatch, user: UserDep, services: ServicesDep) -> UserOut:
    if not valid_tz(body.tz):
        raise ValidationFailed("Unknown time zone. Use an IANA name like Asia/Kathmandu.")
    repo.set_tz(services.system, user.id, body.tz)
    updated = repo.get(services.system, user.id)
    assert updated is not None
    return user_out(services, updated)
