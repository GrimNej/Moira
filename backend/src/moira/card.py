"""The card for one memory (§4.3.6, App. N.4). Date strings are computed here, in code."""

import json
import sqlite3
from typing import Any

from moira.capture.urls import platform
from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as repo
from moira.db.repos.nuggets import Nugget
from moira.domain import timefmt
from moira.errors import NotFound

SOURCE_LABELS = {
    "typed": "Telegram",
    "voice": "a voice note",
    "screenshot": "a screenshot",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "github": "GitHub",
    "web": "the web",
    "x": "X",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "threads": "Threads",
    "video": "a video",
    "forward": "a forwarded message",
    "location": "a location",
    "contact": "a contact",
    "other": "a file",
}
METHOD_LABELS = {
    "web_search": "web search",
    "youtube_oembed": "YouTube",
    "github_api": "GitHub",
    "page_fetch": "the page",
    "image": "the screenshot",
    "video": "the video",
    "pdf": "the PDF",
    "asr": "your voice note",
}


def title_of(conn: sqlite3.Connection, n: Nugget) -> str:
    e = repo.enrichment(conn, n.id)
    if e is not None:
        return str(e["title"])
    return (n.user_text or n.content_text or "Saved item").splitlines()[0][:80]


def _sent_source(conn: sqlite3.Connection, n: Nugget) -> str:
    raws = repo.raw_events_for(conn, n.id)
    channel = raws[0]["channel"] if raws else "web"
    if n.source in ("voice", "screenshot", "video", "forward"):
        return SOURCE_LABELS[n.source]
    return {
        "telegram": "Telegram",
        "web": "the web app",
        "share": "the share sheet",
        "demo": "Telegram",
        "import": "an import",
    }.get(channel, "Telegram")


def build(conn: sqlite3.Connection, public_id: str, *, now_ms: int, tz: str) -> dict[str, Any]:
    n = repo.by_public_id(conn, public_id)
    if n is None or n.deleted_at is not None:
        raise NotFound("That memory is gone.")
    e = repo.enrichment(conn, n.id)
    primary = hubs_repo.primary_hub(conn, n.id)
    members = hubs_repo.memberships(conn, n.id)
    is_earlier = any(m.role in ("earlier", "corrected") for m in members) and not any(
        m.role == "current" for m in members
    )

    now_line = None
    earlier: list[dict[str, Any]] = []
    replaced_by = None
    for m in members:
        hub = hubs_repo.get(conn, m.hub_id)
        if hub is None or hub.kind not in ("fact", "person"):
            continue
        if hub.now_line and now_line is None:
            now_line = hub.now_line
        if m.role == "current":
            for old in hubs_repo.members(conn, hub.id, ("earlier", "corrected")):
                on = repo.get(conn, old.nugget_id)
                if on is not None:
                    earlier.append(
                        {
                            "id": on.public_id,
                            "title": title_of(conn, on),
                            "until": old.until or on.captured_at,
                        }
                    )
        elif m.role in ("earlier", "corrected") and replaced_by is None:
            for cur in hubs_repo.members(conn, hub.id, ("current",)):
                cn = repo.get(conn, cur.nugget_id)
                if cn is not None and cn.captured_at >= n.captured_at:
                    replaced_by = {
                        "id": cn.public_id,
                        "title": title_of(conn, cn),
                        "t": cn.captured_at,
                    }
                    break

    found = None
    research = [r for r in repo.research_for(conn, n.id) if r["status"] == "ok"]
    if research:
        r = research[-1]
        text = " · ".join(p for p in (r["title"], r["author"], r["findings"]) if p)
        found = {
            "method": METHOD_LABELS.get(r["method"], r["method"]),
            "text": text or (r["excerpt"] or "")[:600],
            "verified": None if r["verified"] is None else bool(r["verified"]),
            "sources": json.loads(r["sources"])[:5],
        }
    elif n.content_text:
        found = {
            "method": "the screenshot" if n.source == "screenshot" else "the attachment",
            "text": n.content_text[:1200],
            "verified": None,
            "sources": [],
        }

    lst: list[str] = []
    if e is not None and e["structured_list"]:
        lst = list(json.loads(e["structured_list"]).get("items", []))

    before = repo.previous(conn, n)
    nearby: list[dict[str, Any]] = []
    if primary is not None:
        rows = conn.execute(
            "SELECT n.id FROM hub_members m JOIN nuggets n ON n.id = m.nugget_id"
            " WHERE m.hub_id = ? AND n.id <> ? AND n.deleted_at IS NULL"
            " ORDER BY ABS(n.captured_at - ?) LIMIT 3",
            (primary.id, n.id, n.captured_at),
        ).fetchall()
        for (nid,) in rows:
            o = repo.get(conn, nid)
            if o is not None:
                nearby.append({"id": o.public_id, "title": title_of(conn, o), "t": o.captured_at})

    kind = e["kind"] if e is not None else ("link" if n.url else "note")
    source_label = SOURCE_LABELS.get(n.source, n.source)
    if n.url and n.source == "web":
        source_label = platform(n.url.split("/")[2]) if "//" in n.url else "the web"
    return {
        "id": n.public_id,
        "title": title_of(conn, n),
        "kind": kind,
        "hub": {"id": primary.public_id, "name": primary.name}
        if primary
        else {"id": "", "name": ""},
        "isEarlier": is_earlier,
        "now": now_line,
        "replacedBy": replaced_by,
        "earlier": earlier,
        "sent": {
            "text": n.user_text,
            "source": n.source,
            "sourceLabel": _sent_source(conn, n),
            "t": n.captured_at,
            "localTime": timefmt.time_only(n.captured_at, tz),
        },
        "list": lst,
        "found": found,
        "guess": e["guess"] if e is not None else "",
        "saved": {
            "t": n.captured_at,
            "local": timefmt.full(n.captured_at, tz),
            "relative": timefmt.relative(n.captured_at, now_ms, tz),
        },
        "before": {
            "id": before.public_id,
            "title": title_of(conn, before),
            "gap": timefmt.gap(before.captured_at, n.captured_at),
        }
        if before is not None
        else None,
        "nearby": nearby,
        "sourceName": source_label,
    }
