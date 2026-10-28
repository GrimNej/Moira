"""Shared fixtures. Tests never read a real .env and never call external services."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from moira.config import Settings

# Synthetic values only (AGENTS.md: never real tokens in tests).
TEST_ENV = {
    "APP_ENV": "test",
    "PUBLIC_BASE_URL": "https://moira.test",
    "TELEGRAM_BOT_TOKEN": "123456:TEST-not-a-real-token",
    "TELEGRAM_BOT_USERNAME": "moira_test_bot",
    "OWNER_TELEGRAM_ID": "1000001",
}


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
