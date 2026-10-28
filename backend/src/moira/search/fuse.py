"""Reciprocal rank fusion (§8.2): rrf(d) = Σ wᵢ / (60 + rankᵢ(d))."""

RRF_K = 60


def rrf(
    channels: dict[str, list[int]], weights: dict[str, float], k: int = RRF_K
) -> dict[int, float]:
    score: dict[int, float] = {}
    for name, ranked in channels.items():
        w = weights.get(name, 1.0)
        for rank, nid in enumerate(ranked, start=1):
            score[nid] = score.get(nid, 0.0) + w / (k + rank)
    return score


def which_channels(channels: dict[str, list[int]]) -> dict[int, list[str]]:
    """For clue labels: the channels that found each id."""
    found: dict[int, list[str]] = {}
    for name, ranked in channels.items():
        for nid in ranked:
            found.setdefault(nid, []).append(name)
    return found
