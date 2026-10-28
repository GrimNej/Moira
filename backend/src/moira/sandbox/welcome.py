"""The static Welcome sky (§4.3.2): the sample memory's sky payload, served by Caddy."""

import json
from pathlib import Path

from moira import sky
from moira.db.connection import open_db
from moira.memory.create import get_meta


def write_welcome_sky(template: Path, out: Path) -> None:
    conn = open_db(template, readonly=True)
    try:
        now = int(get_meta(conn, "template_now") or 0)
        data = sky.payload(conn, now_ms=now)
        data["template_now"] = now
    finally:
        conn.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
