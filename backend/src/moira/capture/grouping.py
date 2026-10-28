"""Capture grouping in Telegram (§7.1.1): a link and its caption sent apart become one nugget."""

import json
import sqlite3
from dataclasses import dataclass

from moira.capture.urls import find_urls

BARE_KINDS = ("photo", "album", "voice", "video", "forward")
MAX_CAPTION = 280


@dataclass(frozen=True, slots=True)
class Part:
    kind: str
    text: str
    media_group_id: str | None = None


def is_bare(part: Part) -> bool:
    """A link with no other words, media without caption, a voice note, a plain forward."""
    text = part.text.strip()
    if part.kind == "forward":
        return True
    if part.kind in BARE_KINDS:
        return not text
    urls = find_urls(text)
    if urls:
        rest = text
        for u in urls:
            rest = rest.replace(u, "")
        return not rest.strip()
    return False


def is_caption(part: Part) -> bool:
    return (
        part.kind in ("text", "link")
        and 0 < len(part.text.strip()) <= MAX_CAPTION
        and not is_bare(part)
    )


def should_merge(previous: Part, new: Part) -> bool:
    """Rule 2 of §7.1.1 (rule 1, the open file job, is checked by the caller)."""
    if previous.media_group_id and previous.media_group_id == new.media_group_id:
        return True
    prev_bare, new_bare = is_bare(previous), is_bare(new)
    if prev_bare == new_bare:
        return False
    other = new if prev_bare else previous
    return is_caption(other)


def first_part(conn: sqlite3.Connection, nugget_id: int) -> Part | None:
    row = conn.execute(
        "SELECT kind, text, media_meta FROM raw_events WHERE nugget_id = ? AND edit_of IS NULL"
        " ORDER BY id LIMIT 1",
        (nugget_id,),
    ).fetchone()
    if row is None:
        return None
    meta = json.loads(row["media_meta"]) if row["media_meta"] else {}
    return Part(row["kind"], row["text"] or "", meta.get("media_group_id"))


def group_count(conn: sqlite3.Connection, nugget_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM raw_events WHERE nugget_id = ? AND edit_of IS NULL", (nugget_id,)
    ).fetchone()
    return int(row[0])
