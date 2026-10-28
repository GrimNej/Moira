"""The service container shared by the API, the bot and the worker (§5.2 one process).

Built once in the lifespan; tests build it with a FixedClock, a temp DATA_DIR and FakeLLM.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from moira.capture.service import CaptureService
from moira.clock import Clock
from moira.config import Settings
from moira.db.connection import open_db
from moira.db.migrate import migrate
from moira.db.repos import users as users_repo
from moira.db.repos.users import User
from moira.embed.model import Embedder
from moira.jobs.queue import Queue
from moira.memory.registry import Memories


@dataclass
class Services:
    settings: Settings
    clock: Clock
    system: sqlite3.Connection
    memories: Memories
    queue: Queue
    embedder: Embedder | None
    capture: CaptureService
    # Filled in as later layers are built (AI client, search, filing, ...).
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def tmp_dir(self):  # type: ignore[no-untyped-def]  # Path
        path = self.settings.data_dir / "tmp"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def user_by_telegram(self, telegram_id: int) -> User | None:
        user = users_repo.by_telegram_id(self.system, telegram_id)
        if user is None or user.disabled:
            return None
        if user.expires_at is not None and user.expires_at <= self.clock.now_ms():
            return None
        return user


def build_services(settings: Settings, clock: Clock, embedder: Embedder | None) -> Services:
    data = settings.data_dir
    for sub in ("memories", "sandboxes", "templates", "tmp"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    system = open_db(data / "system.db")
    migrate(system, "system")
    memories = Memories(data, clock, embed_model=settings.embed_model, embed_dim=settings.embed_dim)
    queue = Queue(system, clock)
    capture = CaptureService(
        system=system, memories=memories, queue=queue, clock=clock, embedder=embedder
    )
    return Services(settings, clock, system, memories, queue, embedder, capture)
