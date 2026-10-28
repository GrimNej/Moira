"""Build the sample memory (§11.3) by running the real capture and filing pipeline in time order.

Readers are disabled (sample URLs are fake); research rows come from the JSONL and are marked
as sample. Every nugget gets ``is_sample = 1``. ``meta.template_now`` records "now".
Used by ``scripts/build_demo_db.py``, the eval harness and tests.
"""

import json
import random
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from moira.capture.service import CaptureInput
from moira.clock import FixedClock, to_ms
from moira.config import Settings
from moira.db.connection import open_db
from moira.db.migrate import migrate
from moira.db.repos import jobs as jobs_repo
from moira.db.repos import nuggets as nuggets_repo
from moira.db.repos import users
from moira.embed.model import Embedder
from moira.jobs.queue import Queue
from moira.jobs.worker import Worker
from moira.memory.create import set_meta
from moira.memory.registry import Memories
from moira.services import Services

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "data" / "demo" / "nuggets.jsonl"
TZ = "Asia/Kathmandu"


@dataclass
class Built:
    path: Path
    template_now: int
    keys: dict[str, str]  # anchor key → nugget public id


def load_rows(path: Path = DEMO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def build_template(
    out: Path,
    *,
    settings: Settings,
    llm: Any,
    embedder: Embedder | None,
    now: datetime,
    rows: list[dict[str, Any]] | None = None,
) -> Built:
    from moira.app_services import build_handlers, wire
    from moira.capture.service import CaptureService
    from moira.readers.base import ReaderResult

    rows = rows if rows is not None else load_rows()
    zone = ZoneInfo(TZ)
    now = now.astimezone(zone)
    work = Path(tempfile.mkdtemp(prefix="moira-demo-"))
    clock = FixedClock(now)
    system = open_db(work / "system.db")
    migrate(system, "system")
    memories = Memories(work, clock, embed_model=settings.embed_model, embed_dim=settings.embed_dim)
    queue = Queue(system, clock, rng=random.Random(11))  # noqa: S311
    user = users.create(
        system,
        public_id="u_sampledemoxx",
        kind="judge",
        memory_path="template.db",
        tz=TZ,
        now=to_ms(now),
    )
    # A high id so a real-model build never charges its spend to a real user's cap.
    system.execute("UPDATE users SET id = 900000001 WHERE id = ?", (user.id,))
    user = users.get(system, 900000001)  # type: ignore[assignment]
    assert user is not None
    capture = CaptureService(
        system=system, memories=memories, queue=queue, clock=clock, embedder=embedder
    )
    services = Services(settings, clock, system, memories, queue, embedder, capture)
    wire(services, llm)

    async def no_reader(url: str) -> ReaderResult:
        return ReaderResult("page_fetch", "skipped")

    services.extras["read_link"] = no_reader
    worker = Worker(queue, build_handlers(services))
    conn = memories.open("template.db", "template")
    keys: dict[str, str] = {}
    for row in rows:
        day = now.date() - timedelta(days=int(row["day_offset"]))
        when = datetime(
            day.year, day.month, day.day, int(row["hour"]), int(row["minute"]), tzinfo=zone
        )
        clock.set(min(when, now))
        source = row.get("source", "typed")
        kind = "photo" if source == "screenshot" else "text"
        r = capture.capture(
            CaptureInput(channel="demo", kind=kind, text=row.get("text", ""), is_sample=True),
            user,
        )
        if r.nugget is None:
            continue
        n = r.nugget
        if row.get("key"):
            keys[str(row["key"])] = n.public_id
        for kind_ in ("read_link", "research"):
            for j in jobs_repo.pending_for_ref(system, user.id, n.public_id, (kind_,)):
                jobs_repo.mark(system, j.id, "cancelled", clock.now_ms(), None)
        if source in ("voice", "screenshot"):
            nuggets_repo.set_source(conn, n.id, source, clock.now_ms())
        if row.get("image_text"):
            nuggets_repo.append_content_text(conn, n.id, str(row["image_text"]), clock.now_ms())
        res = row.get("research")
        if res:
            nuggets_repo.insert_research(
                conn,
                n.id,
                method=res["method"],
                status="ok",
                now=clock.now_ms(),
                title=res.get("title", ""),
                author=res.get("author", ""),
                findings=res.get("findings", ""),
                sources=res.get("sources", []),
                verified=None if res.get("verified") is None else bool(res["verified"]),
            )
        for _ in range(8):
            clock.advance(timedelta(seconds=30))
            await worker.run_once()
    clock.set(now)
    await worker.run_once()
    conn.execute("UPDATE nuggets SET is_sample = 1")
    set_meta(conn, "template_now", str(to_ms(now)))
    set_meta(conn, "kind", "template")
    set_meta(conn, "sample_keys", json.dumps(keys))
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    dst = open_db(out)
    conn.backup(dst)
    dst.close()
    memories.close_all()
    system.close()
    shutil.rmtree(work, ignore_errors=True)
    return Built(out, to_ms(now), keys)
