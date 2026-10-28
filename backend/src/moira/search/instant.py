"""Instant retrieval (§8.2), no AI: five channels fused with RRF, then the priors.

``raw_search`` keeps the raw-text path (FTS, trigram, exact) used before filing and in
degraded mode; ``retrieve`` is the full instant tier.
"""

import re
import sqlite3
from dataclasses import dataclass

from moira.embed.model import Embedder
from moira.search import exact, fts, priors
from moira.search.fuse import rrf, which_channels
from moira.search.hubs import hub_channel, people_channel
from moira.search.parse import Parsed

PHRASE = re.compile(r'"([^"]{2,})"')
WEIGHTS = {"fts": 1.0, "vector": 1.0, "exact": 2.0, "hubs": 0.6, "people": 1.5}


@dataclass(frozen=True, slots=True)
class Hit:
    nugget_id: int
    score: float
    channels: tuple[str, ...]


def raw_search(conn: sqlite3.Connection, text: str, tz: str, limit: int = 40) -> list[Hit]:
    phrases = PHRASE.findall(text)
    terms = fts.words(PHRASE.sub(" ", text))
    channels = {
        "fts": fts.search(conn, terms + phrases, 100),
        "exact": exact.search(conn, text, phrases, tz, 50),
    }
    scores = rrf(channels, WEIGHTS)
    found = which_channels(channels)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], -kv[0]))[:limit]
    return [Hit(nid, s, tuple(found[nid])) for nid, s in ordered]


def channels_for(
    conn: sqlite3.Connection,
    p: Parsed,
    tz: str,
    embedder: Embedder | None,
    enabled: frozenset[str] = frozenset(WEIGHTS),
) -> dict[str, list[int]]:
    """Run every enabled channel (the eval's ablation ladder switches them off)."""
    query_text = " ".join(p.terms + p.phrases)
    out: dict[str, list[int]] = {}
    if "fts" in enabled:
        out["fts"] = fts.search(conn, p.terms + p.phrases, 100)
    qvec = None
    if embedder is not None and query_text and ("vector" in enabled or "hubs" in enabled):
        from moira.search import vectors

        qvec = embedder.encode([query_text])[0]
        if "vector" in enabled:
            out["vector"] = [nid for nid, _ in vectors.knn(conn, "vec_nuggets", qvec, 100)]
    if "exact" in enabled:
        exact_text = (
            " ".join(e.value for e in p.exact)
            + " "
            + " ".join(t for t in p.text.split() if re.search(r"[@.#/_\d-]", t))
        )
        out["exact"] = (
            exact.search(conn, exact_text, p.phrases, tz, 50) if exact_text.strip() else []
        )
    if "hubs" in enabled:
        out["hubs"] = hub_channel(conn, p.terms, qvec)
    if "people" in enabled:
        out["people"] = people_channel(conn, p.text)
    # Live ids only (KNN can return soft-deleted rows).
    live = _live(conn, {i for ids in out.values() for i in ids})
    return {k: [i for i in v if i in live] for k, v in out.items()}


def _live(conn: sqlite3.Connection, ids: set[int]) -> set[int]:
    if not ids:
        return set()
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id FROM nuggets WHERE id IN ({marks}) AND deleted_at IS NULL",  # noqa: S608
        list(ids),
    ).fetchall()
    return {r[0] for r in rows}


def apply_priors(
    conn: sqlite3.Connection, scores: dict[int, float], p: Parsed, use_time_source: bool = True
) -> dict[int, float]:
    if not scores:
        return {}
    ids = list(scores)
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        "SELECT n.id, n.captured_at, n.source, e.kind, COALESCE(s.importance, 0.5) AS imp,"  # noqa: S608
        " (SELECT GROUP_CONCAT(role) FROM hub_members m WHERE m.nugget_id = n.id) AS roles"
        f" FROM nuggets n LEFT JOIN enrichments e ON e.nugget_id = n.id"
        f" LEFT JOIN stars s ON s.nugget_id = n.id WHERE n.id IN ({marks})",
        ids,
    ).fetchall()
    out = {}
    for r in rows:
        score = scores[r["id"]]
        if use_time_source:
            if p.time is not None:
                score *= priors.time_prior(r["captured_at"], p.time)
            score *= priors.source_prior(r["source"], p.source)
        score *= priors.kind_prior(r["kind"], p.kinds)
        score *= priors.history_prior(set((r["roles"] or "").split(",")), p.wants_past)
        score *= priors.importance_prior(r["imp"])
        out[r["id"]] = score
    return out


def retrieve(
    conn: sqlite3.Connection,
    p: Parsed,
    tz: str,
    embedder: Embedder | None,
    *,
    limit: int = 40,
    enabled: frozenset[str] = frozenset(WEIGHTS),
    use_priors: bool = True,
) -> list[Hit]:
    channels = channels_for(conn, p, tz, embedder, enabled)
    scores = rrf(channels, WEIGHTS)
    if use_priors:
        scores = apply_priors(conn, scores, p)
    if not scores and use_priors:
        return time_only(conn, p, limit)
    found = which_channels(channels)
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], -kv[0]))[:limit]
    return [Hit(nid, s, tuple(found.get(nid, ()))) for nid, s in ordered]


def time_only(conn: sqlite3.Connection, p: Parsed, limit: int = 40) -> list[Hit]:
    """When a question is only a time or a source ("what did I save yesterday?")."""
    if p.time is None and p.source is None:
        return []
    rows = conn.execute(
        "SELECT id, captured_at, source FROM nuggets WHERE deleted_at IS NULL"
        " ORDER BY captured_at DESC LIMIT 2000"
    ).fetchall()
    scored = []
    for r in rows:
        s = 1.0
        if p.time is not None:
            s *= priors.time_prior(r["captured_at"], p.time)
        s *= priors.source_prior(r["source"], p.source)
        scored.append((r["id"], s))
    scored.sort(key=lambda x: -x[1])
    return [Hit(nid, s, ("time",)) for nid, s in scored[:limit] if s > 0.05]
