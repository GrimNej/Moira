"""T47: sandboxes and judge copies of the sample memory (§11.4–11.5)."""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from moira import accounts
from moira.ai.fake import FakeLLM
from moira.ai.usage import Budget
from moira.config import load_settings
from moira.db.repos import usage as ledger
from moira.db.repos import users as users_repo
from moira.demo import build_template, load_rows
from moira.errors import AiBudgetExceeded
from moira.main import create_app
from moira.memory.create import create_memory, get_meta
from moira.sandbox import SAMPLE_TZ
from moira.sandbox.gc import sandbox_gc
from moira.sandbox.rebase import HOUR_MS, REBASED
from moira.sandbox.service import SampleNotReady, create_sandbox, template_path
from moira.services import Services
from tests.conftest import TEST_ENV

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    import asyncio

    out = tmp_path_factory.mktemp("tpl") / "demo.db"
    rows = load_rows()[:12]
    with pytest.MonkeyPatch.context() as mp:
        for key, value in TEST_ENV.items():
            mp.setenv(key, value)
        mp.setenv("DATA_DIR", str(out.parent / "data"))
        settings = load_settings()
    built = asyncio.run(
        build_template(out, settings=settings, llm=FakeLLM(), embedder=None, now=T0, rows=rows)
    )
    return built.path


@pytest.fixture
def ready(app: Services, template: Path) -> Services:
    dst = template_path(app)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(template, dst)
    return app


def test_every_time_column_is_rebased(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=0, embed_model="x", embed_dim=8)
    tables = [
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not r[0].startswith("sqlite_")
    ]
    found = set()
    for t in tables:
        for col in conn.execute(f"PRAGMA table_info({t})"):
            name, typ = col[1], (col[2] or "").upper()
            if typ == "INTEGER" and (name.endswith("_at") or name in ("since", "until")):
                found.add((t, name))
    assert found, "the schema has time columns"
    assert found <= set(REBASED), f"not rebased: {sorted(found - set(REBASED))}"


def test_sandbox_is_a_rebased_copy(ready: Services, template: Path) -> None:
    ready.clock.advance(timedelta(days=40))  # a judging day long after the template was built
    user = create_sandbox(ready)
    assert user.kind == "sandbox" and user.tz == SAMPLE_TZ
    assert user.expires_at == ready.clock.now_ms() + 24 * HOUR_MS
    conn = ready.memories.open(user.memory_path)
    newest = conn.execute("SELECT MAX(captured_at) FROM nuggets").fetchone()[0]
    count = conn.execute("SELECT COUNT(*) FROM nuggets").fetchone()[0]
    assert count >= 10
    from moira.db.connection import open_db

    src = open_db(template, readonly=True)
    tpl_newest = src.execute("SELECT MAX(captured_at) FROM nuggets").fetchone()[0]
    tpl_now = int(get_meta(src, "template_now") or 0)
    src.close()
    # Relative ages are preserved and anchored to now − 2 h.
    assert newest - (ready.clock.now_ms() - 2 * HOUR_MS) == tpl_newest - tpl_now
    assert int(get_meta(conn, "template_now") or 0) == ready.clock.now_ms()


def test_judges_get_their_own_copy(ready: Services) -> None:
    from datetime import date

    code = accounts.create_invite(ready, "judge", 5, date(2026, 11, 20))
    judge = accounts.redeem_invite(ready, code, 4242, "Judge")
    assert judge is not None and judge.kind == "judge" and judge.tz == SAMPLE_TZ
    n = ready.memories.open(judge.memory_path).execute("SELECT COUNT(*) FROM nuggets").fetchone()
    assert n[0] >= 10


def test_no_template_means_a_clear_error(app: Services) -> None:
    with pytest.raises(SampleNotReady):
        create_sandbox(app)


def test_at_most_max_active_oldest_evicted(ready: Services) -> None:
    ready.settings.sandbox_max_active = 2
    first = create_sandbox(ready)
    ready.clock.advance(timedelta(minutes=1))
    create_sandbox(ready)
    ready.clock.advance(timedelta(minutes=1))
    create_sandbox(ready)
    assert users_repo.get(ready.system, first.id) is None
    assert not ready.memories.path(first.memory_path).exists()
    assert users_repo.count_kind(ready.system, "sandbox", ready.clock.now_ms()) == 2


def test_expired_sandboxes_are_deleted(ready: Services) -> None:
    user = create_sandbox(ready)
    path = ready.memories.path(user.memory_path)
    assert path.exists()
    ready.clock.advance(timedelta(hours=23))
    assert sandbox_gc(ready) == 0
    ready.clock.advance(timedelta(hours=2))
    assert sandbox_gc(ready) == 1
    assert users_repo.get(ready.system, user.id) is None
    assert not path.exists()


def test_a_sandbox_cannot_exceed_its_cap(ready: Services) -> None:
    user = create_sandbox(ready)
    budget: Budget = ready.extras["budget"]
    cap = ready.settings.cap_sandbox_daily_usd
    budget.check(user_id=user.id, estimate=cap / 2)
    budget.record(
        ledger.UsageRow(
            user_id=user.id,
            day_utc=budget.day(),
            kind="answer",
            model="m",
            est_usd=cap * 0.9,
            ok=True,
            created_at=ready.clock.now_ms(),
        )
    )
    with pytest.raises(AiBudgetExceeded):
        budget.check(user_id=user.id, estimate=cap * 0.2)


async def test_post_sandbox_signs_in_with_a_cookie(ready: Services) -> None:
    transport = httpx.ASGITransport(app=create_app(services=ready))
    async with httpx.AsyncClient(
        transport=transport, base_url="https://moira.test", headers={"X-Moira": "1"}
    ) as c:
        r = await c.post("/api/sandbox")
        assert r.status_code == 201, r.text
        assert r.json()["user"]["kind"] == "sandbox"
        assert "moira_session" in r.headers.get("set-cookie", "") or r.cookies
        me = await c.get("/api/me")
        assert me.status_code == 200 and me.json()["tz"] == SAMPLE_TZ
        sky = await c.get("/api/sky")
        assert len(sky.json()["stars"]["id"]) >= 10
