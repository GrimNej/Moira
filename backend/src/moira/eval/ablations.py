"""The ablation ladder (§12.3): each config adds one thing."""

import sqlite3
from dataclasses import dataclass

from moira.embed.model import Embedder
from moira.search import fts
from moira.search.fuse import rrf
from moira.search.instant import WEIGHTS, apply_priors, channels_for
from moira.search.parse import Parsed


@dataclass(frozen=True)
class Config:
    name: str
    fts_columns: tuple[str, ...]
    channels: frozenset[str]
    priors: bool
    answer: bool
    deep: bool


RAW = ("user_text",)
ENRICHED = ("title", "summary", "tags", "user_text", "content_text", "research")
ALL_COLS = (*ENRICHED, "questions", "hub_names")

CONFIGS = {
    "A": Config("A", RAW, frozenset({"fts"}), False, False, False),
    "B": Config("B", ENRICHED, frozenset({"fts"}), False, False, False),
    "C": Config("C", ALL_COLS, frozenset({"fts"}), False, False, False),
    "D": Config("D", ALL_COLS, frozenset({"fts", "vector", "exact"}), False, False, False),
    "E": Config("E", ALL_COLS, frozenset(WEIGHTS), False, False, False),
    "F": Config("F", ALL_COLS, frozenset(WEIGHTS), True, False, False),
    "G": Config("G", ALL_COLS, frozenset(WEIGHTS), True, True, False),
    "H": Config("H", ALL_COLS, frozenset(WEIGHTS), True, True, True),
}


def fts_columns(conn: sqlite3.Connection, terms: list[str], cols: tuple[str, ...]) -> list[int]:
    q = fts.fts_query(terms)
    if not q:
        return []
    rows = conn.execute(
        f"SELECT f.rowid FROM nugget_fts f JOIN nuggets n ON n.id = f.rowid"  # noqa: S608
        f" WHERE nugget_fts MATCH ? AND n.deleted_at IS NULL ORDER BY {fts.BM25} LIMIT 100",
        (f"{{{' '.join(cols)}}} : ({q})",),
    ).fetchall()
    return [r[0] for r in rows]


def retrieve(
    conn: sqlite3.Connection, p: Parsed, cfg: Config, tz: str, embedder: Embedder | None
) -> list[int]:
    channels = channels_for(conn, p, tz, embedder, cfg.channels)
    channels["fts"] = fts_columns(conn, p.terms + p.phrases, cfg.fts_columns)
    scores = rrf(channels, WEIGHTS)
    if cfg.priors:
        scores = apply_priors(conn, scores, p)
    if not scores and cfg.priors:
        from moira.search.instant import time_only

        return [h.nugget_id for h in time_only(conn, p)]
    return [nid for nid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], -kv[0]))][:40]
