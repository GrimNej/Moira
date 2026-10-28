"""Versions of the raw text (§7.10). The raw layer changes only here (invariant 4)."""

import sqlite3

from moira.db.repos import nuggets as repo
from moira.db.repos.nuggets import Nugget
from moira.db.repos.users import User
from moira.services import Services


def history(conn: sqlite3.Connection, nugget_id: int) -> list[dict[str, object]]:
    """Every earlier text with when and how it was edited, oldest first."""
    return [
        {
            "version": r["version"],
            "user_text": r["user_text"],
            "edited_at": r["edited_at"],
            "edited_via": r["edited_via"],
        }
        for r in repo.versions(conn, nugget_id)
    ]


def web_edit(services: Services, user: User, nugget: Nugget, new_text: str) -> Nugget | None:
    """A web Edit: a raw event and a version, then an edit_refile job (same path as Telegram)."""
    conn = services.memories.open(user.memory_path)
    raws = repo.raw_events_for(conn, nugget.id)
    first = next((r for r in raws if r["edit_of"] is None), None)
    external = f"web:{nugget.public_id}"
    if first is None or first["external_id"] is None:
        # Web saves have no external id: give the first raw event one so edits chain to it.
        if first is not None:
            conn.execute(
                "UPDATE raw_events SET external_id = ? WHERE id = ?", (external, first["id"])
            )
            channel = first["channel"]
        else:
            return None
    else:
        external, channel = first["external_id"], first["channel"]
    return services.capture.edit(user, channel, external, new_text, via="web_edit")
