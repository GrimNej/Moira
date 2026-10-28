"""T25: deterministic placement; 5,000 synthetic stars never closer than 9 units; centres fixed."""

import itertools
import math
from pathlib import Path

import numpy as np
import pytest

from moira.db.repos import hubs, nuggets, stars
from moira.domain.text import name_norm
from moira.memory.create import create_memory
from moira.memory.importance import importance
from moira.memory.placement import Grid, place_hub_center, place_star
from moira.search import vectors


def seed_nugget(conn, i: int) -> nuggets.Nugget:  # type: ignore[no-untyped-def]
    return nuggets.insert(
        conn,
        public_id=f"n_{i:012d}",
        source="typed",
        user_text=f"note {i}",
        captured_at=i,
        captured_tz="UTC",
        now=i,
    )


def test_star_placement_is_deterministic(tmp_path: Path) -> None:
    results = []
    for run in range(2):
        conn = create_memory(tmp_path / f"m{run}.db", kind="user", now=1)
        shelf = hubs.shelves(conn)[0]
        pos = []
        for i in range(30):
            n = seed_nugget(conn, i)
            hubs.add_member(
                conn,
                hub_id=shelf.id,
                nugget_id=n.id,
                role="member",
                since=i,
                decided_by="ai",
                is_primary=True,
            )
            x, y = place_star(
                conn, nugget_id=n.id, public_id=n.public_id, hub_id=shelf.id, vec=None
            )
            stars.insert(conn, n.id, x, y, now=i)
            pos.append((round(x, 6), round(y, 6)))
        results.append(pos)
    assert results[0] == results[1]


def test_neighbours_pull_a_star_toward_similar_ones(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    shelf = hubs.shelves(conn)[0]
    rng = np.random.default_rng(1)
    a = rng.normal(size=256).astype(np.float32)
    a /= np.linalg.norm(a)
    b = -a
    placed = {}
    for i, v in enumerate([a, a, b, b]):
        n = seed_nugget(conn, i)
        hubs.add_member(
            conn,
            hub_id=shelf.id,
            nugget_id=n.id,
            role="member",
            since=i,
            decided_by="ai",
            is_primary=True,
        )
        vectors.upsert(conn, "vec_nuggets", n.id, v)
        x, y = place_star(conn, nugget_id=n.id, public_id=n.public_id, hub_id=shelf.id, vec=v)
        stars.insert(conn, n.id, x, y, now=i)
        placed[i] = (x, y)
    new = seed_nugget(conn, 99)
    hubs.add_member(
        conn,
        hub_id=shelf.id,
        nugget_id=new.id,
        role="member",
        since=99,
        decided_by="ai",
        is_primary=True,
    )
    x, y = place_star(conn, nugget_id=new.id, public_id=new.public_id, hub_id=shelf.id, vec=a)
    near_a = min(math.dist((x, y), placed[0]), math.dist((x, y), placed[1]))
    near_b = min(math.dist((x, y), placed[2]), math.dist((x, y), placed[3]))
    assert near_a < near_b


def test_five_thousand_stars_never_closer_than_nine(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    shelves = hubs.shelves(conn)
    grid = Grid()
    positions = []
    conn.execute("BEGIN")
    for i in range(5000):
        hub = shelves[i % 3]
        n = seed_nugget(conn, i)
        hubs.add_member(
            conn,
            hub_id=hub.id,
            nugget_id=n.id,
            role="member",
            since=i,
            decided_by="ai",
            is_primary=True,
        )
        x, y = place_star(
            conn, nugget_id=n.id, public_id=n.public_id, hub_id=hub.id, vec=None, grid=grid
        )
        stars.insert(conn, n.id, x, y, now=i)
        positions.append((x, y))
    conn.execute("COMMIT")
    arr = np.array(positions)
    # Check with a fine grid instead of 12.5M pairs.
    cells: dict[tuple[int, int], list[int]] = {}
    for idx, (x, y) in enumerate(arr):
        cells.setdefault((int(x // 9), int(y // 9)), []).append(idx)
    for (cx, cy), members in cells.items():
        near = list(
            itertools.chain.from_iterable(
                cells.get((cx + dx, cy + dy), []) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            )
        )
        for i in members:
            d = np.hypot(*(arr[near] - arr[i]).T)
            d = d[np.array(near) != i]
            assert d.size == 0 or d.min() >= 9.0 - 1e-6


def test_hub_centres_never_move(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    before = {(h.id, h.x, h.y) for h in hubs.all_hubs(conn)}
    for i in range(20):
        x, y = place_hub_center(conn, (0.0, -1100.0), f"h_seed{i}")
        h = hubs.create(
            conn,
            public_id=f"h_{i:012d}",
            name=f"Topic {i}",
            name_norm=name_norm(f"Topic {i}"),
            kind="topic",
            x=x,
            y=y,
            now=i,
        )
        assert all(math.dist((x, y), (o.x, o.y)) >= 1 for o in hubs.all_hubs(conn) if o.id != h.id)
    after = {(h.id, h.x, h.y) for h in hubs.all_hubs(conn)}
    assert before <= after  # every earlier centre is unchanged


def test_new_hub_keeps_its_distance(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    x, y = place_hub_center(conn, (0.0, -1100.0), "h_seed")
    assert min(math.dist((x, y), (h.x, h.y)) for h in hubs.all_hubs(conn)) >= 220


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        (
            {
                "age_days": 0,
                "open_count": 0,
                "saved_count": 1,
                "is_current_fact": False,
                "has_research": False,
                "pinned": False,
            },
            0.50,
        ),
        (
            {
                "age_days": 10_000,
                "open_count": 0,
                "saved_count": 1,
                "is_current_fact": False,
                "has_research": False,
                "pinned": False,
            },
            0.20,
        ),
        (
            {
                "age_days": 0,
                "open_count": 9,
                "saved_count": 4,
                "is_current_fact": True,
                "has_research": True,
                "pinned": True,
            },
            1.0,
        ),
    ],
)
def test_importance_formula(kw: dict[str, object], expected: float) -> None:
    assert importance(**kw) == pytest.approx(expected, abs=1e-6)  # type: ignore[arg-type]
