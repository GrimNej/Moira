"""Star importance (§7.7.3): brightness and size. Recomputed nightly and when a star is opened."""

import math
import sqlite3

from moira.db.repos import stars as stars_repo

DAY_MS = 86_400_000


def importance(
    *,
    age_days: float,
    open_count: int,
    saved_count: int,
    is_current_fact: bool,
    has_research: bool,
    pinned: bool,
) -> float:
    value = (
        0.20
        + 0.30 * math.exp(-age_days / 120)
        + 0.20 * min(1.0, math.log(1 + open_count) / math.log(10))
        + 0.10 * min(1.0, math.log(max(1, saved_count)) / math.log(4))
        + 0.15 * int(is_current_fact)
        + 0.05 * int(has_research)
        + 0.10 * int(pinned)
    )
    return max(0.0, min(1.0, value))


def recompute(conn: sqlite3.Connection, now_ms: int, nugget_ids: list[int] | None = None) -> int:
    """Recompute importance for all (or some) placed stars. Returns how many were updated."""
    sql = (
        "SELECT n.id, n.captured_at, n.open_count, n.saved_count, n.pinned,"
        " EXISTS(SELECT 1 FROM hub_members m JOIN hubs h ON h.id = m.hub_id"
        "        WHERE m.nugget_id = n.id AND m.role = 'current' AND h.kind IN ('fact','person'))"
        "   AS cur,"
        " EXISTS(SELECT 1 FROM research r WHERE r.nugget_id = n.id AND r.status = 'ok') AS res"
        " FROM nuggets n JOIN stars s ON s.nugget_id = n.id WHERE n.deleted_at IS NULL"
    )
    args: list[int] = []
    if nugget_ids is not None:
        if not nugget_ids:
            return 0
        sql += f" AND n.id IN ({','.join('?' * len(nugget_ids))})"
        args = list(nugget_ids)
    values = []
    for r in conn.execute(sql, args).fetchall():
        values.append(
            (
                importance(
                    age_days=max(0.0, (now_ms - r["captured_at"]) / DAY_MS),
                    open_count=r["open_count"],
                    saved_count=r["saved_count"],
                    is_current_fact=bool(r["cur"]),
                    has_research=bool(r["res"]),
                    pinned=bool(r["pinned"]),
                ),
                r["id"],
            )
        )
    stars_repo.set_importance(conn, values)
    return len(values)
