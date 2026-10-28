"""T50: backups, the export zip, /export in the bot and forget everything."""

import json
import sqlite3
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from moira.backup import backup as bk
from moira.capture.service import CaptureInput
from moira.db.repos import users as users_repo
from moira.jobs import maintenance
from moira.main import create_app
from moira.sandbox import service as sandbox_service
from moira.services import Services
from tests.conftest import World, run_jobs
from tests.integration.test_api_memories import client


async def seed(app: Services, world: World) -> None:
    for text in ["buy oat milk", "Josh's email is josh.r@example.com"]:
        app.capture.capture(CaptureInput(channel="web", text=text), world.owner)
    await run_jobs(app)


async def test_export_zip_holds_jsonl_markdown_and_sqlite(app: Services, world: World) -> None:
    await seed(app, world)
    async with client(app, world.owner) as c:
        r = await c.get("/api/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    path = Path(app.tmp_dir) / "got.zip"
    path.write_bytes(r.content)
    with zipfile.ZipFile(path) as z:
        assert set(z.namelist()) == {"memories.jsonl", "memories.md", "memory.sqlite"}
        rows = [json.loads(line) for line in z.read("memories.jsonl").decode().splitlines()]
        assert {r["text"] for r in rows} >= {"buy oat milk"}
        assert "buy oat milk" in z.read("memories.md").decode()
        z.extract("memory.sqlite", app.tmp_dir)
    copy = sqlite3.connect(Path(app.tmp_dir) / "memory.sqlite")
    assert copy.execute("SELECT COUNT(*) FROM nuggets").fetchone()[0] == 2
    copy.close()
    # Only the downloaded copy is left: the server-side zip was deleted after sending.
    assert not list(Path(app.tmp_dir).glob("*.export.zip"))


async def test_export_is_refused_for_sandboxes(app: Services, world: World) -> None:
    app.extras["seed_memory"] = lambda path: None
    user = sandbox_service.create_sandbox(app)
    async with client(app, user) as c:
        r = await c.get("/api/export")
    assert r.status_code == 403


async def test_incremental_export_to_telegram(app: Services, world: World) -> None:
    await seed(app, world)
    with app.system:
        users_repo.upsert_chat(app.system, chat_id=77, user_id=world.owner.id, now=0)
    bot = AsyncMock()
    assert await maintenance.send_export(app, world.owner, bot=bot, chat_id=77) == "sent"
    assert bot.send_document.await_count == 1
    assert await maintenance.send_export(app, world.owner, bot=bot, chat_id=77) == "empty"
    app.clock.advance(timedelta(minutes=1))
    app.capture.capture(CaptureInput(channel="web", text="call the dentist"), world.owner)
    await run_jobs(app)
    assert await maintenance.send_export(app, world.owner, bot=bot, chat_id=77) == "sent"
    assert not list(Path(app.tmp_dir).glob("*.export.zip"))


async def test_forget_everything_after_grace_and_cancel(app: Services, world: World) -> None:
    await seed(app, world)
    async with client(app, world.owner) as c:
        r = await c.post("/api/forget-everything")
        assert r.status_code == 200
        due = r.json()["scheduled_for"]
        assert due == app.clock.now_ms() + 24 * 3_600_000
        assert (await c.delete("/api/forget-everything")).status_code == 204
        await c.post("/api/forget-everything")
    await run_jobs(app)  # within the grace period nothing happens
    conn = app.memories.open(world.owner.memory_path)
    assert conn.execute("SELECT COUNT(*) FROM nuggets").fetchone()[0] == 2
    app.clock.advance(timedelta(hours=25))
    await run_jobs(app)
    conn = app.memories.open(world.owner.memory_path)
    assert conn.execute("SELECT COUNT(*) FROM nuggets").fetchone()[0] == 0


async def test_cancelled_forget_does_nothing(app: Services, world: World) -> None:
    await seed(app, world)
    async with client(app, world.owner) as c:
        await c.post("/api/forget-everything")
        await c.delete("/api/forget-everything")
    app.clock.advance(timedelta(hours=25))
    await run_jobs(app)
    conn = app.memories.open(world.owner.memory_path)
    assert conn.execute("SELECT COUNT(*) FROM nuggets").fetchone()[0] == 2


async def test_backup_snapshots_checks_and_uploads(app: Services, world: World) -> None:
    await seed(app, world)
    data = app.settings.data_dir
    (data / "sandboxes").mkdir(exist_ok=True)
    (data / "sandboxes" / "s_x.db").write_bytes(b"")
    staging = data / "backups" / "staging"
    taken = bk.snapshot(data, staging)
    names = {p.relative_to(staging).as_posix() for p in taken}
    assert "system.db" in names
    assert any(n.startswith("memories/") for n in names)
    assert not any("sandboxes" in n for n in names)
    bk.check_integrity(taken)

    calls: list[list[str]] = []
    out = data / "backups" / "x.age"
    bk.upload(
        out, "oci:b", sunday=True, settings=app.settings, runner=lambda c: calls.append(list(c))
    )
    assert calls[0] == ["rclone", "copy", str(out), "oci:b/daily/"]
    assert calls[1] == ["rclone", "copy", str(out), "oci:b/weekly/"]
    assert ["rclone", "delete", "--min-age", "14d", "oci:b/daily/"] in calls
    assert ["rclone", "delete", "--min-age", "56d", "oci:b/weekly/"] in calls

    bk.record(data, app.clock.now(), 1234, "ok")
    assert json.loads((data / "backups" / "last.json").read_text())["status"] == "ok"
    assert "Last backup:" in maintenance.digest_text(app)


def test_a_corrupt_snapshot_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    try:
        bk.check_integrity([bad])
    except (bk.BackupFailed, sqlite3.DatabaseError):
        return
    raise AssertionError("a corrupt file passed integrity_check")


async def test_export_route_mounts(app: Services) -> None:
    transport = httpx.ASGITransport(app=create_app(services=app))
    async with httpx.AsyncClient(transport=transport, base_url="https://moira.test") as c:
        assert (await c.get("/api/export")).status_code == 401
