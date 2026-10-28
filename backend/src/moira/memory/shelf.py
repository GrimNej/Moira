"""Shelf fallback map (§7.4.5): every nugget belongs to at least one hub (principle 6)."""

import re
import sqlite3

from moira.db.repos import hubs as hubs_repo
from moira.db.repos import nuggets as nuggets_repo
from moira.db.repos.hubs import Hub

WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Watch list", re.compile(r"(?i)\b(?:watch|movie|film|series|episode|show|anime|trailer)s?\b")),
    ("Music", re.compile(r"(?i)\b(?:song|album|playlist|artist|band|track|music|singer)s?\b")),
    (
        "Places",
        re.compile(r"(?i)\b(?:place|cafe|café|trail|hotel|museum|restaurant|park|trek)s?\b"),
    ),
    (
        "Learning",
        re.compile(r"(?i)\b(?:learn|course|tutorial|lesson|book|study|class)(?:s|ing)?\b"),
    ),
    (
        "Tech & setup",
        re.compile(
            r"(?i)\b(?:pc|gpu|cpu|bios|driver|setup|settings|install|router|laptop|fps)s?\b"
        ),
    ),
)


def shelf_name_for(kind: str, source: str, text: str) -> str:
    if kind == "person":
        return "People"
    if kind == "todo":
        return "To-dos"
    if kind == "idea":
        return "Ideas"
    if source in ("location",):
        return "Places"
    if kind == "link" and source == "youtube":
        return "Watch list"
    for name, pattern in WORDS:
        if pattern.search(text):
            return name
    if kind == "link" or source in (
        "web",
        "github",
        "instagram",
        "x",
        "tiktok",
        "facebook",
        "threads",
    ):
        return "Links & reads"
    return "Misc"


def shelf_by_name(conn: sqlite3.Connection, name: str) -> Hub:
    for hub in hubs_repo.shelves(conn):
        if hub.name == name:
            return hub
    raise LookupError(name)


def fallback_shelf(conn: sqlite3.Connection, nugget_id: int, kind: str | None = None) -> Hub:
    n = nuggets_repo.get(conn, nugget_id)
    assert n is not None
    if kind is None:
        e = nuggets_repo.enrichment(conn, nugget_id)
        kind = e["kind"] if e is not None else ("link" if n.url else "note")
    return shelf_by_name(conn, shelf_name_for(kind, n.source, n.user_text + " " + n.content_text))
