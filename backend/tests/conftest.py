"""Shared fixtures. Tests never read a real .env and never call external services."""

import random
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from moira.capture.service import CaptureService
from moira.clock import FixedClock
from moira.config import Settings
from moira.db.connection import open_db
from moira.db.migrate import migrate
from moira.db.repos import users
from moira.db.repos.users import User
from moira.embed.model import HashEmbedder
from moira.jobs.queue import Queue
from moira.memory.registry import Memories

# Synthetic values only (AGENTS.md: never real tokens in tests).
TEST_ENV = {
    "APP_ENV": "test",
    "PUBLIC_BASE_URL": "https://moira.test",
    "TELEGRAM_BOT_TOKEN": "123456:TEST-not-a-real-token",
    "TELEGRAM_BOT_USERNAME": "moira_test_bot",
    "OWNER_TELEGRAM_ID": "1000001",
}
NPT = ZoneInfo("Asia/Kathmandu")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Run every test in a temp dir (no stray .env) with only the test variables set."""
    for key in Settings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)
    yield


@dataclass
class World:
    """A temp system.db + memories + queue + capture service around a FixedClock."""

    clock: FixedClock
    system: sqlite3.Connection
    memories: Memories
    queue: Queue
    capture: CaptureService
    owner: User
    data_dir: Path

    def memory(self, user: User | None = None) -> sqlite3.Connection:
        return self.memories.open((user or self.owner).memory_path)


@pytest.fixture
def world(tmp_path: Path) -> World:
    data = tmp_path / "data"
    clock = FixedClock(datetime(2026, 10, 26, 21, 0, tzinfo=NPT))
    system = open_db(data / "system.db")
    migrate(system, "system")
    memories = Memories(data, clock, embed_model="hash", embed_dim=256)
    queue = Queue(system, clock, rng=random.Random(3))
    owner = users.create(
        system,
        public_id="u_ownerownerow",
        kind="owner",
        memory_path="memories/u_ownerownerow.db",
        tz="Asia/Kathmandu",
        now=clock.now_ms(),
        telegram_id=1000001,
    )
    capture = CaptureService(
        system=system, memories=memories, queue=queue, clock=clock, embedder=HashEmbedder(256)
    )
    return World(clock, system, memories, queue, capture, owner, data)


@pytest.fixture
def services(world: World):  # type: ignore[no-untyped-def]
    """A Services container around the world fixture (settings from the test env)."""
    from moira.config import load_settings
    from moira.services import Services

    settings = load_settings()
    return Services(
        settings=settings,
        clock=world.clock,
        system=world.system,
        memories=world.memories,
        queue=world.queue,
        embedder=world.capture.embedder,
        capture=world.capture,
    )


@pytest.fixture
def app(services):  # type: ignore[no-untyped-def]
    """Services wired with FakeLLM, the bus and every job handler."""
    from moira.ai.fake import FakeLLM
    from moira.app_services import wire

    return wire(services, FakeLLM())


async def run_jobs(app, minutes: int = 4) -> int:  # type: ignore[no-untyped-def]
    """Advance the clock past debounce and preconditions and run every ready job."""
    from datetime import timedelta

    from moira.app_services import build_handlers
    from moira.jobs.worker import Worker

    worker = Worker(app.queue, build_handlers(app))
    total = 0
    for _ in range(minutes * 2):
        app.clock.advance(timedelta(seconds=30))
        total += await worker.run_once()
    return total
