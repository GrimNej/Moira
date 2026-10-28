"""Shift every time in a copied sample memory so relative anchors stay true (§11.4).

"Two weeks ago" in the template is two weeks ago on any judging day.
"""

import sqlite3

from moira.memory.create import set_meta

# (table, column). A test asserts this covers every INTEGER column named *_at, since or until.
REBASED: tuple[tuple[str, str], ...] = (
    ("nuggets", "captured_at"),
    ("nuggets", "original_posted_at"),
    ("nuggets", "created_at"),
    ("nuggets", "updated_at"),
    ("nuggets", "deleted_at"),
    ("raw_events", "received_at"),
    ("raw_events", "original_posted_at"),
    ("nugget_versions", "edited_at"),
    ("enrichments", "created_at"),
    ("enrichments", "updated_at"),
    ("research", "created_at"),
    ("research", "next_retry_at"),
    ("hubs", "created_at"),
    ("hubs", "updated_at"),
    ("hub_members", "since"),
    ("hub_members", "until"),
    ("hub_events", "created_at"),
    ("people", "created_at"),
    ("stars", "placed_at"),
    ("conversations", "created_at"),
    ("turns", "created_at"),
)

HOUR_MS = 3_600_000


def delta_for(now_ms: int, template_now_ms: int) -> int:
    """Δ = now − template_now − 2 h (§11.4): the newest sample item is two hours old."""
    return now_ms - template_now_ms - 2 * HOUR_MS


def rebase(conn: sqlite3.Connection, delta_ms: int, now_ms: int) -> None:
    with conn:
        for table, column in REBASED:
            # Names come from the constant above, never from input.
            conn.execute(
                f"UPDATE {table} SET {column} = {column} + ? WHERE {column} IS NOT NULL",  # noqa: S608
                (delta_ms,),
            )
        set_meta(conn, "template_now", str(now_ms))
