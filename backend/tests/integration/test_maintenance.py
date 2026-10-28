"""T48: nightly work, tidy gates, the digest, timers and the tmp sweep (FixedClock)."""

import json
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from moira import ids
from moira.ai.schemas import Merge, Rename, TidyOutput
from moira.ai.tidy import MAX_CHANGES, apply, candidates
from moira.capture.service import CaptureInput
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import jobs as jobs_repo
from moira.db.repos import usage as ledger
from moira.db.repos import users as users_repo
from moira.domain.text import name_norm
from moira.jobs import maintenance, timers
from moira.memory.undo import undo_group
from moira.services import Services
from tests.conftest import World, run_jobs


def hub(conn, name: str, kind: str = "topic"):  # type: ignore[no-untyped-def]
    return hubs_repo.create(
        conn, public_id=ids.new("h_"), name=name, name_norm=name_norm(name), kind=kind,
        x=0, y=0, now=0,
    )  # fmt: skip


async def seed(app: Services, world: World) -> None:
    for text in ["PC fix: turn on XMP", "buy oat milk", "my favorite fruit is apple"]:
        app.capture.capture(CaptureInput(channel="web", text=text), world.owner)
    await run_jobs(app)


async def test_nightly_recomputes_importance(app: Services, world: World) -> None:
    await seed(app, world)
    out = await maintenance.nightly(app, world.owner)
    assert out["importance"] >= 3
    assert out["repaired"] == 0
    assert out["secrets"] == 0


def test_tidy_applies_at_most_five_changes(app: Services, world: World) -> None:
    conn = app.memories.open(world.owner.memory_path)
    made = [hub(conn, f"Topic {i}") for i in range(8)]
    proposal = TidyOutput(
        merges=[],
        renames=[
            Rename(hub_id=h.public_id, new_name=f"Clear name {i}", reason="r", confidence=0.95)
            for i, h in enumerate(made)
        ],
    )
    changes = apply(conn, proposal, candidates(conn), now=1, embedder=None)
    assert len(changes) == MAX_CHANGES


def test_tidy_gates(app: Services, world: World) -> None:
    conn = app.memories.open(world.owner.memory_path)
    a, b = hub(conn, "PC setup fixes"), hub(conn, "PC fixes")
    c = hub(conn, "Cooking")
    josh, joshua = hub(conn, "Josh", "person"), hub(conn, "Joshua", "person")
    low = TidyOutput(
        merges=[
            Merge(
                keep_hub_id=a.public_id,
                merge_hub_ids=[b.public_id],
                new_name="",
                reason="",
                confidence=0.8,
            )
        ],
        renames=[Rename(hub_id=c.public_id, new_name="Food", reason="", confidence=0.85)],
    )
    assert apply(conn, low, candidates(conn), now=1, embedder=None) == []
    unlike = TidyOutput(
        merges=[
            Merge(
                keep_hub_id=a.public_id,
                merge_hub_ids=[c.public_id],
                new_name="",
                reason="",
                confidence=0.99,
            ),
            Merge(
                keep_hub_id=josh.public_id,
                merge_hub_ids=[joshua.public_id],
                new_name="",
                reason="",
                confidence=0.99,
            ),
        ],
        renames=[],
    )
    assert apply(conn, unlike, candidates(conn), now=1, embedder=None) == []


def test_tidy_merge_moves_members_and_undoes(app: Services, world: World) -> None:
    conn = app.memories.open(world.owner.memory_path)
    keep, other = hub(conn, "PC setup fixes"), hub(conn, "PC fixes")
    r = app.capture.capture(CaptureInput(channel="web", text="XMP on"), world.owner)
    assert r.nugget is not None
    nid = r.nugget.id
    hubs_repo.add_member(conn, hub_id=other.id, nugget_id=nid, role="member", since=1,
                         decided_by="ai", is_primary=True)  # fmt: skip
    out = TidyOutput(
        merges=[
            Merge(
                keep_hub_id=keep.public_id,
                merge_hub_ids=[other.public_id],
                new_name="",
                reason="",
                confidence=0.9,
            )
        ],
        renames=[],
    )
    [change] = apply(conn, out, candidates(conn), now=5, embedder=None)
    assert hubs_repo.member(conn, keep.id, nid) is not None
    assert hubs_repo.member(conn, other.id, nid) is None
    archived = hubs_repo.get(conn, other.id)
    assert archived is not None and archived.archived and archived.merged_into == keep.id
    with conn:
        assert undo_group(conn, change.group_id, now=6)
    assert hubs_repo.member(conn, other.id, nid) is not None
    assert hubs_repo.member(conn, keep.id, nid) is None
    back = hubs_repo.get(conn, other.id)
    assert back is not None and not back.archived


def test_digest_lists_spend_dead_jobs_and_backups(app: Services, world: World) -> None:
    now = app.clock.now()
    yesterday = (now.astimezone(maintenance.NPT) - timedelta(days=1)).date().isoformat()
    ledger.insert(
        app.system,
        ledger.UsageRow(
            user_id=world.owner.id,
            day_utc=yesterday,
            kind="answer",
            model="m",
            est_usd=0.5,
            ok=True,
            created_at=app.clock.now_ms(),
            input_tokens=1000,
            cached_tokens=600,
        ),
    )
    job_id = app.queue.enqueue(world.owner.id, "read_link", ref="n_1")
    jobs_repo.mark(app.system, job_id, "dead", app.clock.now_ms() - 3_600_000, "boom")
    marker = app.settings.data_dir / "backups" / "last.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"when": "2026-03-01 03:00", "status": "ok"}))
    text = maintenance.digest_text(app)
    assert "AI spend: $0.50" in text
    assert "answer: 60% cached" in text
    assert "Dead jobs: 1 (read_link)" in text
    assert "Last backup: 2026-03-01 03:00 (ok)" in text
    assert "Saves: owner" in text


def test_timers_fire_at_local_times(app: Services, world: World) -> None:
    tz = ZoneInfo(world.owner.tz)
    before = datetime(2026, 3, 2, 3, 29, tzinfo=tz).astimezone(UTC)
    after = before + timedelta(minutes=2)
    kinds = {k for _, k in timers.due(app, before, after)}
    assert "nightly" in kinds
    npt8 = datetime(2026, 3, 2, 8, 0, tzinfo=maintenance.NPT).astimezone(UTC)
    kinds = {k for _, k in timers.due(app, npt8 - timedelta(minutes=1), npt8)}
    assert "digest" in kinds and "nightly" not in kinds
    assert timers.enqueue_due(app, npt8 - timedelta(minutes=1), npt8) >= 1
    assert timers.enqueue_due(app, npt8 - timedelta(minutes=1), npt8) == 0  # no duplicates
    assert users_repo.owner(app.system) is not None


def test_tmp_sweep_removes_old_leftovers(app: Services) -> None:
    tmp = app.tmp_dir
    old, fresh = tmp / "old.upload", tmp / "fresh.upload"
    old.write_bytes(b"x")
    fresh.write_bytes(b"x")
    t = (app.clock.now_ms() - 2 * 3_600_000) / 1000
    os.utime(old, (t, t))
    t2 = app.clock.now_ms() / 1000
    os.utime(fresh, (t2, t2))
    assert maintenance.tmp_sweep(app) == 1
    assert not old.exists() and fresh.exists()
