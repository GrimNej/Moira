"""Priors after fusion (§8.2): time (telescoping-aware), source, kind, history, importance."""

import math

from moira.search.timeexpr import TimeHint

DAY_MS = 86_400_000
TELESCOPE = 1.6  # older items: people remember distant events as more recent


def time_prior(t_ms: int, hint: TimeHint) -> float:
    """1.0 inside an explicit window; otherwise a Gaussian, widened ×1.6 on the older side."""
    lo, hi = hint.window_from_ms, hint.window_to_ms
    if lo is not None or hi is not None:
        if (lo is None or t_ms >= lo) and (hi is None or t_ms < hi):
            return 1.0
        edge = lo if lo is not None and t_ms < lo else hi
        assert edge is not None
        diff = (t_ms - edge) / DAY_MS
    else:
        diff = (t_ms - hint.target_ms) / DAY_MS
    sigma = hint.sigma_days * (TELESCOPE if diff < 0 else 1.0)
    return max(0.04, math.exp(-0.5 * (diff / sigma) ** 2))


def source_prior(item_source: str, wanted: str | None) -> float:
    if wanted is None:
        return 1.0
    return 1.7 if item_source == wanted else 0.2


def kind_prior(item_kind: str | None, wanted: list[str]) -> float:
    return 1.3 if wanted and item_kind in wanted else 1.0


def history_prior(roles: set[str], wants_past: bool) -> float:
    if roles & {"earlier", "corrected"}:
        return 1.2 if wants_past else 0.55
    return 1.0


def importance_prior(importance: float) -> float:
    return 0.85 + 0.3 * importance
