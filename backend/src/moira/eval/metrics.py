"""Retrieval and answer metrics (§12.1)."""

import statistics
from dataclasses import dataclass, field


@dataclass
class QueryResult:
    qid: str
    category: str
    expected: list[int]
    ranked: list[int]
    top_cite: int | None = None
    not_found: bool = False
    hallucinated: int = 0
    seconds: float = 0.0
    usd: float = 0.0


@dataclass
class Metrics:
    n: int
    r1: float
    r5: float
    mrr10: float
    top_cite: float | None
    nf_precision: float | None
    hallucinated: int
    p50_s: float
    usd_per_q: float
    by_category: dict[str, float] = field(default_factory=dict)


def rank_of(expected: list[int], ranked: list[int]) -> int | None:
    for i, nid in enumerate(ranked, start=1):
        if nid in expected:
            return i
    return None


def compute(results: list[QueryResult], with_answers: bool) -> Metrics:
    answerable = [r for r in results if r.expected]
    unanswerable = [r for r in results if not r.expected]
    ranks = [rank_of(r.expected, r.ranked) for r in answerable]
    n = max(1, len(answerable))
    r1 = sum(1 for k in ranks if k == 1) / n
    r5 = sum(1 for k in ranks if k is not None and k <= 5) / n
    mrr = sum(1 / k for k in ranks if k is not None and k <= 10) / n
    by_cat: dict[str, list[int]] = {}
    for r, k in zip(answerable, ranks, strict=True):
        by_cat.setdefault(r.category, []).append(1 if k is not None and k <= 5 else 0)
    top_cite = nf = None
    if with_answers:
        top_cite = sum(1 for r in answerable if r.top_cite in r.expected) / n
        said_nf = [r for r in results if r.not_found]
        nf = (
            (sum(1 for r in said_nf if not r.expected) / len(said_nf))
            if said_nf
            else (1.0 if not unanswerable else 0.0)
        )
    secs = [r.seconds for r in results] or [0.0]
    return Metrics(
        n=len(results),
        r1=r1,
        r5=r5,
        mrr10=mrr,
        top_cite=top_cite,
        nf_precision=nf,
        hallucinated=sum(r.hallucinated for r in results),
        p50_s=statistics.median(secs),
        usd_per_q=sum(r.usd for r in results) / max(1, len(results)),
        by_category={k: sum(v) / len(v) for k, v in by_cat.items()},
    )
