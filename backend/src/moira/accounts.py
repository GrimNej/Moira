"""Accounts: the owner, testers and judges by invite (§11.5). Invite codes are stored hashed."""

import hashlib
import secrets
from datetime import UTC, date, datetime

from moira import ids
from moira.clock import to_ms
from moira.db.repos import users as repo
from moira.db.repos.users import User, UserKind
from moira.services import Services


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def create_invite(services: Services, role: str, uses: int, until: date) -> str:
    """Return a new invite code (shown once); only its hash is stored."""
    if role not in ("tester", "judge"):
        raise ValueError(role)
    code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
    expires = to_ms(datetime(until.year, until.month, until.day, 23, 59, tzinfo=UTC))
    repo.create_invite(
        services.system, code_hash=hash_code(code), role=role, max_uses=uses, expires_at=expires
    )
    return code


def _new_user(
    services: Services,
    kind: UserKind,
    telegram_id: int | None,
    name: str,
    expires_at: int | None = None,
) -> User:
    public_id = ids.new("u_")
    folder = "sandboxes" if kind == "sandbox" else "memories"
    memory_path = f"{folder}/{public_id}.db"
    seed = services.extras.get("seed_memory")
    if seed is not None and kind == "judge":
        seed(memory_path)  # a private copy of the sample memory (T47)
    services.memories.open(memory_path, "sandbox" if kind == "sandbox" else "user")
    return repo.create(
        services.system,
        public_id=public_id,
        kind=kind,
        memory_path=memory_path,
        tz=services.settings.default_tz,
        now=services.clock.now_ms(),
        telegram_id=telegram_id,
        display_name=name,
        expires_at=expires_at,
    )


def ensure_owner(services: Services, telegram_id: int, name: str) -> User | None:
    """The owner is whoever has OWNER_TELEGRAM_ID; created on their first /start."""
    if telegram_id != services.settings.owner_telegram_id:
        return None
    existing = repo.by_telegram_id(services.system, telegram_id)
    if existing is not None:
        return existing
    return _new_user(services, "owner", telegram_id, name)


def redeem_invite(services: Services, code: str, telegram_id: int, name: str) -> User | None:
    existing = repo.by_telegram_id(services.system, telegram_id)
    if existing is not None:
        return existing
    role = repo.use_invite(services.system, hash_code(code), services.clock.now_ms())
    if role is None:
        return None
    expires = None
    if role == "judge":
        u = services.settings.judge_access_until
        expires = to_ms(datetime(u.year, u.month, u.day, 23, 59, tzinfo=UTC))
    return _new_user(services, "judge" if role == "judge" else "tester", telegram_id, name, expires)


def create_sandbox_user(services: Services, expires_at: int) -> User:
    return _new_user(services, "sandbox", None, "Sample memory", expires_at)
