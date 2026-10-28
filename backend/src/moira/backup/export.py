"""The user's export: a zip with JSONL, Markdown and a SQLite copy (App. B, §13.14).

Built in tmp and deleted after sending. Sandboxes cannot export (the data is the sample).
"""

import json
import secrets as pysecrets
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from moira.db.repos import export as repo

MAX_TELEGRAM_BYTES = 50 * 1024 * 1024


def _when(ms: int, tz: str) -> str:
    return (
        datetime.fromtimestamp(ms / 1000, UTC).astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")
    )


def records(conn: sqlite3.Connection, since: int | None) -> list[dict[str, object]]:
    out = []
    for r in repo.nuggets_since(conn, since):
        out.append(
            {
                "id": r["public_id"],
                "saved_at": r["captured_at"],
                "time_zone": r["captured_tz"],
                "source": r["source"],
                "kind": r["kind"],
                "title": r["title"],
                "text": r["user_text"],
                "read_from_attachment": r["content_text"] or None,
                "url": r["url"],
                "constellations": json.loads(r["hubs"] or "[]"),
                "summary": r["summary"],
                "version": r["version"],
            }
        )
    return out


def markdown(items: list[dict[str, object]], tz: str) -> str:
    lines = ["# Moira export", ""]
    for it in reversed(items):
        title = it["title"] or str(it["text"])[:60] or "(untitled)"
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"*{_when(int(str(it['saved_at'])), tz)} · {it['source']}*")
        if it["constellations"]:
            lines.append(f"*{', '.join(map(str, it['constellations']))}*")  # type: ignore[call-overload]
        lines.append("")
        if it["text"]:
            lines.append(str(it["text"]))
            lines.append("")
        if it["url"]:
            lines.append(f"<{it['url']}>")
            lines.append("")
        if it["read_from_attachment"]:
            lines.append("> " + str(it["read_from_attachment"]).replace("\n", "\n> "))
            lines.append("")
    return "\n".join(lines)


def build(
    conn: sqlite3.Connection, tmp: Path, tz: str, *, since: int | None = None, sqlite: bool = True
) -> Path:
    """Write the zip into ``tmp`` and return its path. The caller deletes it."""
    tmp.mkdir(parents=True, exist_ok=True)
    stem = pysecrets.token_hex(8)
    out = tmp / f"{stem}.export.zip"
    items = records(conn, since)
    copy = tmp / f"{stem}.memory.sqlite"
    try:
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "memories.jsonl",
                "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in items),
            )
            z.writestr("memories.md", markdown(items, tz))
            if sqlite:
                dst = sqlite3.connect(copy)
                try:
                    conn.backup(dst)
                finally:
                    dst.close()
                z.write(copy, "memory.sqlite")
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    finally:
        copy.unlink(missing_ok=True)
    return out
