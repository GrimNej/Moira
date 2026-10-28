"""T33: metrics are computed the way §12.1 defines them."""

import pytest

from moira.eval.metrics import QueryResult, compute, rank_of


def test_rank_and_metrics() -> None:
    results = [
        QueryResult("a", "exact", [1], [1, 2, 3], top_cite=1),
        QueryResult("b", "vague", [9], [1, 2, 3, 4, 9], top_cite=2),
        QueryResult("c", "vague", [7], [1, 2], top_cite=None),
        QueryResult("d", "unanswerable", [], [1], not_found=True),
    ]
    assert rank_of([9], [1, 2, 3, 4, 9]) == 5
    m = compute(results, with_answers=True)
    assert m.r1 == pytest.approx(1 / 3)
    assert m.r5 == pytest.approx(2 / 3)
    assert m.mrr10 == pytest.approx((1 + 1 / 5) / 3)
    assert m.top_cite == pytest.approx(1 / 3)
    assert m.nf_precision == 1.0
    assert m.by_category["vague"] == 0.5
