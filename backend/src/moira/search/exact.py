"""Exact channel (§8.2): normalized exact lookups plus trigram substring search."""

import re
import sqlite3

from moira.capture.exacts import extract
from moira.db.repos import nuggets as repo
from moira.search.fts import quote

# Tokens worth a substring search: anything with @ . # / _ - or a digit, 3+ characters.
SUBSTRING = re.compile(r"[^\s,;!?()\[\]{}<>\"']{3,}")


def exact_tokens(text: str) -> list[str]:
    """Raw tokens that look like exact strings (emails, handles, colours, codes, partials)."""
    out = []
    for tok in SUBSTRING.findall(text):
        tok = tok.strip(".:'")
        if len(tok) >= 3 and re.search(r"[@.#/_\-\d]", tok):
            out.append(tok)
    return out


def trigram(conn: sqlite3.Connection, needle: str, limit: int = 50) -> list[int]:
    needle = needle.strip()
    if len(needle) < 3:  # the trigram tokenizer needs 3 characters (N.5)
        return []
    rows = conn.execute(
        "SELECT t.rowid FROM nugget_tri t JOIN nuggets n ON n.id = t.rowid"
        " WHERE nugget_tri MATCH ? AND n.deleted_at IS NULL LIMIT ?",
        (quote(needle), limit),
    ).fetchall()
    return [r[0] for r in rows]


def search(
    conn: sqlite3.Connection, text: str, phrases: list[str], tz: str, limit: int = 50
) -> list[int]:
    """Exact normalized matches first, then trigram substrings of tokens and phrases."""
    ranked: list[int] = []

    def add(ids: list[int]) -> None:
        for i in ids:
            if i not in ranked:
                ranked.append(i)

    for e in extract(text, tz):
        add(repo.find_exact(conn, e.kind, e.normalized))
    for tok in exact_tokens(text):
        add(repo.find_exact_prefix(conn, tok.lower().lstrip("@")))
        add(trigram(conn, tok.lstrip("#") if tok.startswith("#") else tok))
    for phrase in phrases:
        add(trigram(conn, phrase))
    return ranked[:limit]
