"""Authentication (§10.2): login links, Mini App initData, sessions. No passwords anywhere."""

import hashlib
import secrets
from datetime import timedelta

from aiogram.utils.web_app import safe_parse_webapp_init_data

from moira.clock import Clock
from moira.db.repos import users as repo
from moira.db.repos.users import User
from moira.errors import Forbidden, MoiraError
from moira.services import Services

COOKIE = "moira_session"
SANDBOX_HOURS = 24


class Unauthorized(MoiraError):
    code = "unauthorized"
    status = 401


def new_token() -> str:
    """32 random bytes, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_login_link(services: Services, user: User) -> str:
    """Store the token's hash for 10 minutes; return the fragment URL (§10.2)."""
    token = new_token()
    now = services.clock.now_ms()
    repo.create_login_token(
        services.system,
        token_hash=hash_token(token),
        user_id=user.id,
        expires_at=now + services.settings.login_token_minutes * 60_000,
    )
    return f"{services.settings.public_base_url}/login#t={token}"


def session_lifetime_ms(services: Services, user: User) -> int:
    if user.kind == "sandbox":
        return SANDBOX_HOURS * 3_600_000
    return services.settings.session_days * 86_400_000


def start_session(services: Services, user: User, via: str) -> str:
    """Create a session and return its raw token (cookie value or bearer)."""
    token = new_token()
    now = services.clock.now_ms()
    expires = now + session_lifetime_ms(services, user)
    if user.expires_at is not None:
        expires = min(expires, user.expires_at)
    repo.create_session(
        services.system,
        id_hash=hash_token(token),
        user_id=user.id,
        now=now,
        expires_at=expires,
        via=via,
    )
    return token


def consume_login_token(services: Services, token: str) -> User:
    user_id = repo.use_login_token(services.system, hash_token(token), services.clock.now_ms())
    if user_id is None:
        raise Unauthorized("This sign-in link has expired or was already used. Send /web again.")
    user = repo.get(services.system, user_id)
    if user is None or user.disabled:
        raise Unauthorized("This account is not available.")
    return user


def telegram_user(services: Services, init_data: str, clock: Clock) -> User:
    """Validate Mini App initData; reject forged or older than 24 h (§10.1, App. G)."""
    try:
        data = safe_parse_webapp_init_data(
            token=services.settings.telegram_bot_token.get_secret_value(), init_data=init_data
        )
    except ValueError:
        raise Unauthorized("Telegram sign-in could not be verified.") from None
    if clock.now() - data.auth_date > timedelta(hours=24):
        raise Unauthorized("Telegram sign-in expired. Open the app again.")
    if data.user is None:
        raise Unauthorized("Telegram sign-in has no user.")
    user = services.user_by_telegram(data.user.id)
    if user is None:
        raise Forbidden("Send /start to the bot first.")
    return user


def resolve(services: Services, token: str | None) -> User | None:
    if not token:
        return None
    now = services.clock.now_ms()
    th = hash_token(token)
    user = repo.session_user(services.system, th, now)
    if user is not None:
        repo.touch_session(services.system, th, now, now + session_lifetime_ms(services, user))
    return user
