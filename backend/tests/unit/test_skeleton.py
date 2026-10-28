"""T03: health endpoint, config validation, ids and clock."""

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from hypothesis import given
from hypothesis import strategies as st

from moira import ids
from moira.clock import FixedClock, SystemClock, from_ms, to_ms
from moira.config import load_settings
from moira.errors import ConfigError
from moira.main import create_app


async def test_health_returns_ok_and_version() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["version"], str) and body["version"]
    assert set(body) == {"ok", "version"}


@pytest.mark.parametrize(
    "name", ["PUBLIC_BASE_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", "OWNER_TELEGRAM_ID"]
)
def test_missing_required_variable_stops_startup_with_its_name(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.delenv(name)
    with pytest.raises(ConfigError, match=name):
        create_app()


def test_prod_requires_model_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(ConfigError, match="MODEL_API_KEY"):
        load_settings()


def test_invalid_variable_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "not-a-number")
    with pytest.raises(ConfigError, match="OWNER_TELEGRAM_ID"):
        load_settings()


def test_defaults_follow_appendix_a() -> None:
    s = load_settings()
    assert s.model_api_base == "https://api.meta.ai/v1"
    assert s.model_main == "muse-spark-1.3"
    assert s.structured_transport == "responses"
    assert s.embed_dim == 256
    assert s.cap_total_usd == 120
    assert s.fake_llm is True


def test_secrets_are_not_printed() -> None:
    s = load_settings()
    assert "TEST-not-a-real-token" not in repr(s)


@pytest.mark.parametrize("prefix", ["n_", "h_", "p_", "u_"])
def test_ids_match_the_public_id_pattern(prefix: str) -> None:
    for _ in range(200):
        assert re.fullmatch(rf"^{prefix}[A-Za-z0-9_-]{{12}}$", ids.new(prefix))


def test_ids_reject_unknown_prefix() -> None:
    with pytest.raises(ValueError, match="prefix"):
        ids.new("x_")


def test_fixed_clock_only_moves_when_told() -> None:
    start = datetime(2026, 10, 26, 21, 0, tzinfo=ZoneInfo("Asia/Kathmandu"))
    clock = FixedClock(start)
    assert clock.now() == start
    assert clock.now().tzinfo == UTC
    clock.advance(timedelta(minutes=5))
    assert clock.now_ms() == to_ms(start) + 5 * 60_000


def test_clocks_refuse_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="aware"):
        FixedClock(datetime(2026, 10, 26))  # noqa: DTZ001


def test_system_clock_is_utc() -> None:
    assert SystemClock().now().tzinfo == UTC


@given(st.integers(min_value=0, max_value=4_102_444_800_000))
def test_ms_round_trip(ms: int) -> None:
    assert to_ms(from_ms(ms)) == ms
