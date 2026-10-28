"""API response models shared by several routes (mirrored in web/src/api/types.ts, App. N.4)."""

from datetime import UTC

from pydantic import BaseModel

from moira.config import app_version
from moira.db.repos import usage
from moira.db.repos.users import User
from moira.services import Services


class Caps(BaseModel):
    spent_today: float
    cap_today: float


class UserOut(BaseModel):
    id: str
    kind: str
    display_name: str
    tz: str
    caps: Caps
    version: str


def cap_for(services: Services, user: User) -> float:
    s = services.settings
    return {
        "owner": s.cap_owner_daily_usd,
        "tester": s.cap_tester_daily_usd,
        "judge": s.cap_judge_daily_usd,
        "sandbox": s.cap_sandbox_daily_usd,
    }[user.kind]


def user_out(services: Services, user: User) -> UserOut:
    day = services.clock.now().astimezone(UTC).strftime("%Y-%m-%d")
    spent = usage.spent_on_day(services.system, day, user.id)
    return UserOut(
        id=user.public_id,
        kind=user.kind,
        display_name=user.display_name,
        tz=user.tz,
        caps=Caps(spent_today=round(spent, 4), cap_today=cap_for(services, user)),
        version=app_version(),
    )
