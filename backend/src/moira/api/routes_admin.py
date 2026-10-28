"""GET /api/admin/stats (owner only, §13.11): counts, spend, queue, errors. No content."""

import os
import shutil
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends

from moira.api.deps import ServicesDep, UserDep, csrf, rate
from moira.db.repos import events, jobs, usage
from moira.db.repos import nuggets as repo
from moira.errors import Forbidden

router = APIRouter(prefix="/api/admin", dependencies=[Depends(csrf)])


def rss_mb() -> float | None:
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None


def stats(services: Any) -> dict[str, Any]:
    now = services.clock.now()
    day = now.astimezone(UTC).strftime("%Y-%m-%d")
    users_by_kind = {
        r[0]: r[1]
        for r in services.system.execute(
            "SELECT kind, COUNT(*) FROM users GROUP BY kind"
        ).fetchall()
    }
    owner = services.system.execute("SELECT memory_path FROM users WHERE kind='owner'").fetchone()
    memories = {}
    if owner is not None:
        conn = services.memories.open(owner[0])
        since = services.clock.now_ms() - 86_400_000
        memories = {
            "nuggets": repo.count_live(conn),
            "feedback_24h": events.feedback_counts(conn, since),
        }
    breaker = getattr(services.extras.get("llm"), "breaker", None)
    disk = shutil.disk_usage(
        services.settings.data_dir if services.settings.data_dir.exists() else os.getcwd()
    )
    return {
        "users": users_by_kind,
        "owner_memory": memories,
        "spend": {
            "today_usd": round(usage.spent_on_day(services.system, day), 4),
            "cap_today_usd": services.settings.cap_global_daily_usd,
            "total_usd": round(usage.spent_total(services.system), 4),
            "cap_total_usd": services.settings.cap_total_usd,
            "by_kind": [dict(r) for r in usage.summary_by_kind(services.system, day)],
        },
        "queue": jobs.count_by_status(services.system),
        "ai_breaker": "open" if breaker is not None and breaker.is_open else "closed",
        "embed": "up" if services.embedder is not None else "down",
        "disk_free_mb": disk.free // (1024 * 1024),
        "rss_mb": rss_mb(),
    }


@router.get("/stats", dependencies=[Depends(rate("admin", 30, 60))])
async def admin_stats(user: UserDep, services: ServicesDep) -> dict[str, Any]:
    if user.kind != "owner":
        raise Forbidden("Owner only.")
    return stats(services)
