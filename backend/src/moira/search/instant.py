"""Instant retrieval (§8.2), no AI. T15: FTS, trigram and exact channels on raw text.

T27 adds the vector, hub and people channels and the priors; this module keeps the
simple raw-text path that capture-time search and degraded mode rely on.
"""

import re
import sqlite3
from dataclasses import dataclass

from moira.search import exact, fts
from moira.search.fuse import rrf, which_channels

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
