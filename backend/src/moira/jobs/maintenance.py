"""Nightly work, the daily digest and housekeeping (§7.0 job table, §7.9, §11.4, §13.15).

``nightly`` runs per memory at 03:30 user time; ``digest`` (08:00 NPT), ``sandbox_gc`` (hourly)
and ``tmp_sweep`` (10 min) are global jobs filed under the owner.
"""

import json
import shutil
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from moira.ai import tidy
from moira.ai.client import LLM
from moira.capture.secrets import detect
from moira.db.repos import jobs as jobs_repo
from moira.db.repos import stats
from moira.db.repos import usage as ledger
from moira.db.repos import users as users_repo
from moira.db.repos.jobs import Job
from moira.db.repos.users import User
from moira.errors import AiBudgetExceeded, AiUnavailable, NotFound
from moira.jobs.worker import Handler
from moira.logging import get_logger
from moira.memory import importance
from moira.memory.indexing import consistency_repair
from moira.sandbox.gc import sandbox_gc
from moira.services import Services

log = get_logger(__name__)
DAY_MS = 86_400_000
TMP_MAX_AGE_MS = 60 * 60_000  # anything in tmp older than an hour is a leftover
NPT = ZoneInfo("Asia/Kathmandu")


async def nightly(services: Services, user: User) -> dict[str, int]:
    conn = services.memories.open(user.memory_path)
    now = services.clock.now_ms()
    out = {"importance": 0, "tidy": 0, "repaired": 0, "secrets": 0}
    async with services.memories.lock(user.memory_path):
        with conn:
            out["importance"] = importance.recompute(conn, now)
        hubs = tidy.candidates(conn)
        if user.kind != "sandbox" and len(hubs) >= 2:
            llm: LLM = services.extras["llm"]
            try:
                proposal = await tidy.propose(llm, conn, hubs, user.id)
            except (AiBudgetExceeded, AiUnavailable) as exc:
                log.info("tidy_skipped", reason=type(exc).__name__)
            else:
                changes = tidy.apply(conn, proposal, hubs, now=now, embedder=services.embedder)
                out["tidy"] = len(changes)
        with conn:
            out["repaired"] = consistency_repair(conn, services.embedder)
        out["secrets"] = sum(
            1 for _, text in stats.unmasked_secret_candidates(conn) if detect(text)
        )
    log.info("nightly_done", **out)
    return out


def tmp_sweep(services: Services) -> int:
    cutoff = services.clock.now_ms() - TMP_MAX_AGE_MS
    gone = 0
    for p in Path(services.tmp_dir).iterdir():
        if p.is_file() and p.stat().st_mtime * 1000 < cutoff:
            p.unlink(missing_ok=True)
            gone += 1
    return gone


def _rss_peak_mb() -> str:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return f"{int(line.split()[1]) // 1024} MB"
    except OSError:
        pass
    return "n/a"


def _last_backup(services: Services) -> str:
    marker = services.settings.data_dir / "backups" / "last.json"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "none recorded"
    return f"{data.get('when', '?')} ({data.get('status', '?')})"


def digest_text(services: Services) -> str:
    """Yesterday in numbers, for the owner (§13.15). Never includes saved content."""
    s = services.settings
    now = services.clock.now()
    today = now.astimezone(NPT).replace(hour=0, minute=0, second=0, microsecond=0)
    start = int((today - timedelta(days=1)).timestamp() * 1000)
    end = int(today.timestamp() * 1000)
    day_utc = (today - timedelta(days=1)).date().isoformat()

    saves: dict[str, int] = {}
    asked: dict[str, int] = {}
    found = not_it = 0
    research = {"verified": 0, "possible": 0, "not_found": 0}
    tidy_lines: list[str] = []
    for u in users_repo.all_active(services.system, services.clock.now_ms()):
        conn = services.memories.open(u.memory_path, "sandbox" if u.kind == "sandbox" else "user")
        saves[u.kind] = saves.get(u.kind, 0) + stats.saves_between(conn, start, end)
        q, f, n = stats.questions_between(conn, start, end)
        asked[u.kind] = asked.get(u.kind, 0) + q
        found, not_it = found + f, not_it + n
        for k, v in stats.research_between(conn, start, end).items():
            research[k] += v
        if u.kind == "owner":
            seen: set[str] = set()
            for row in stats.ai_events_since(conn, start, "tidy"):
                gid = row["group_id"]
                if gid in seen or row["undone"]:
                    continue
                if row["event"] in ("hub_merged", "hub_renamed"):
                    seen.add(gid)
                    after = json.loads(row["after_json"] or "{}")
                    what = after.get("name") or after.get("merged_into") or ""
                    tidy_lines.append(
                        f"  {row['event'].removeprefix('hub_')} → {what}: "
                        f"{s.public_base_url}/?undo={gid}"
                    )

    kinds = ("owner", "tester", "judge", "sandbox")
    rated = found + not_it
    found_rate = f"{round(100 * found / rated)}%" if rated else "n/a"
    spent = ledger.spent_on_day(services.system, day_utc)
    by_kind = ledger.summary_by_kind(services.system, day_utc)
    cache_lines = [
        f"  {r['kind']}: {round(100 * (r['cached'] or 0) / r['input'])}% cached"
        for r in by_kind
        if r["input"]
    ]
    dead = jobs_repo.dead_since(services.system, start)
    disk = shutil.disk_usage(s.data_dir)

    lines = [
        f"Moira, {(today - timedelta(days=1)).strftime('%a %d %b')}",
        "Saves: " + ", ".join(f"{k} {saves.get(k, 0)}" for k in kinds),
        "Questions: " + ", ".join(f"{k} {asked.get(k, 0)}" for k in kinds),
        f"Found it: {found_rate} ({found} of {rated} rated)",
        f"AI spend: ${spent:.2f} of ${s.cap_global_daily_usd:.2f} today; "
        f"${ledger.spent_total(services.system):.2f} of ${s.cap_total_usd:.0f} lifetime",
        *(["Cache:", *cache_lines] if cache_lines else []),
        f"Research: {research['verified']} verified, {research['possible']} possible, "
        f"{research['not_found']} not found",
        f"Dead jobs: {len(dead)}"
        + (f" ({', '.join(sorted({j.kind for j in dead}))})" if dead else ""),
        f"Tidy: {len(tidy_lines)} change(s)",
        *tidy_lines,
        f"Last backup: {_last_backup(services)}",
        f"Disk: {disk.free * 100 // disk.total}% free",
        f"RSS peak: {_rss_peak_mb()}",
    ]
    return "\n".join(lines)


async def send_digest(services: Services) -> str:
    text = digest_text(services)
    from moira.notify import alert_owner

    await alert_owner(services, "digest", text, throttle=False)
    return text


async def forget_everything(services: Services, user: User) -> None:
    """After the 24 h grace (§10.4): the memory file is deleted and an empty one made."""
    async with services.memories.lock(user.memory_path):
        services.memories.close(user.memory_path)
        path = services.memories.path(user.memory_path)
        for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
            p.unlink(missing_ok=True)
        services.memories.open(user.memory_path)
    log.info("forgot_everything")


async def send_export(services: Services, user: User, *, bot: object, chat_id: int) -> str:
    """Incremental export (new and changed since the last one) to the user's Telegram chat."""
    from aiogram.types import FSInputFile

    from moira.backup.export import MAX_TELEGRAM_BYTES, build, records
    from moira.bot import texts

    chat = users_repo.chat(services.system, chat_id)
    since = chat["last_export_at"] if chat is not None else None
    conn = services.memories.open(user.memory_path)
    if not records(conn, since):
        await bot.send_message(chat_id, texts.EXPORT_NOTHING_NEW)  # type: ignore[attr-defined]
        return "empty"
    path = build(conn, Path(services.tmp_dir), user.tz, since=since, sqlite=False)
    try:
        if path.stat().st_size > MAX_TELEGRAM_BYTES:
            link = f"{services.settings.public_base_url}/settings"
            await bot.send_message(chat_id, texts.EXPORT_LINK.format(link=link))  # type: ignore[attr-defined]
            return "link"
        day = services.clock.now().date().isoformat()
        await bot.send_document(  # type: ignore[attr-defined]
            chat_id,
            FSInputFile(path, filename=f"moira-export-{day}.zip"),
            caption=texts.EXPORT_SENT,
        )
        with services.system:
            users_repo.set_chat_last_export(services.system, chat_id, services.clock.now_ms())
        return "sent"
    finally:
        path.unlink(missing_ok=True)


def handlers(services: Services) -> dict[str, Handler]:
    def _user(job: Job) -> User:
        user = users_repo.get(services.system, job.user_id)
        if user is None:
            raise NotFound("user gone")
        return user

    async def nightly_job(job: Job) -> None:
        await nightly(services, _user(job))

    async def digest_job(job: Job) -> None:
        await send_digest(services)

    async def sandbox_gc_job(job: Job) -> None:
        sandbox_gc(services)

    async def tmp_sweep_job(job: Job) -> None:
        tmp_sweep(services)

    async def forget_everything_job(job: Job) -> None:
        await forget_everything(services, _user(job))

    async def export_weekly_job(job: Job) -> None:
        user = _user(job)
        bot = services.extras.get("bot")
        chat = users_repo.chat_for_user(services.system, user.id)
        if bot is not None and chat is not None:
            await send_export(services, user, bot=bot, chat_id=chat["chat_id"])

    return {
        "nightly": nightly_job,
        "digest": digest_job,
        "sandbox_gc": sandbox_gc_job,
        "tmp_sweep": tmp_sweep_job,
        "forget_everything": forget_everything_job,
        "export_weekly": export_weekly_job,
    }
