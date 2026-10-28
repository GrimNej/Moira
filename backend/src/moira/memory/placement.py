"""Sky placement (§7.7): stable by construction. Hub centres and stars never move once placed.

The RNG for a star is seeded with its nugget's public id, so placement is reproducible.
"""

import hashlib
import math
import random
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from moira.db.repos import hubs as hubs_repo
from moira.db.repos import stars as stars_repo
from moira.search import vectors

CELL = 16.0
MIN_GAP = 9.0
GOLDEN = 2.39996


def rng_for(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311  # layout, not security


@dataclass
class Grid:
    """A 16-unit spatial hash for the 9-unit collision check."""

    cells: dict[tuple[int, int], list[tuple[float, float]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def key(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / CELL), math.floor(y / CELL)

    def add(self, x: float, y: float) -> None:
        self.cells[self.key(x, y)].append((x, y))

    def free(self, x: float, y: float, gap: float = MIN_GAP) -> bool:
        cx, cy = self.key(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py in self.cells.get((cx + dx, cy + dy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < gap * gap:
                        return False
        return True

    @classmethod
    def from_db(cls, conn: sqlite3.Connection) -> "Grid":
        g = cls()
        for s in stars_repo.all_live(conn):
            g.add(s.x, s.y)
        return g


def place_hub_center(
    conn: sqlite3.Connection,
    anchor: tuple[float, float],
    seed: str,
) -> tuple[float, float]:
    """§7.7.1: 24 angles at d = 260 + 40·r around the anchor; keep ≥ 220 from all centres."""
    centres = [(h.x, h.y) for h in hubs_repo.all_hubs(conn)]
    rng = rng_for(seed)
    d = 260 + 40 * rng.random()
    best = anchor
    for _ in range(6):
        best_min = -1.0
        for i in range(24):
            a = 2 * math.pi * i / 24
            p = (anchor[0] + d * math.cos(a), anchor[1] + d * math.sin(a))
            m = min((math.dist(p, c) for c in centres), default=math.inf)
            if m > best_min:
                best, best_min = p, m
        if best_min >= 220:
            return best
        d += 60
    return best


def hub_anchor(
    conn: sqlite3.Connection, vec: npt.NDArray[np.float32] | None, fallback: tuple[float, float]
) -> tuple[float, float]:
    """The most similar existing hub centre (cosine of hub vectors), else the fallback shelf."""
    if vec is not None:
        for hid, _ in vectors.knn(conn, "vec_hubs", vec, 1):
            hub = hubs_repo.get(conn, hid)
            if hub is not None:
                return hub.x, hub.y
    return fallback


def place_star(
    conn: sqlite3.Connection,
    *,
    nugget_id: int,
    public_id: str,
    hub_id: int,
    vec: npt.NDArray[np.float32] | None,
    grid: Grid | None = None,
) -> tuple[float, float]:
    """§7.7.2 steps 1–6. Returns the position (the caller stores it once)."""
    hub = hubs_repo.get(conn, hub_id)
    assert hub is not None
    cx, cy = hub.x, hub.y
    rng = rng_for(public_id)
    grid = grid or Grid.from_db(conn)

    placed = conn.execute(
        "SELECT s.nugget_id, s.x, s.y FROM stars s JOIN hub_members m ON m.nugget_id = s.nugget_id"
        " AND m.hub_id = ? AND m.is_primary = 1 JOIN nuggets n ON n.id = s.nugget_id"
        " WHERE n.deleted_at IS NULL AND s.nugget_id <> ?",
        (hub_id, nugget_id),
    ).fetchall()
    members = len(placed) + 1
    neighbours: list[tuple[float, float, float]] = []
    if vec is not None and placed:
        vecs = vectors.many(conn, "vec_nuggets", [r[0] for r in placed])
        scored = []
        for r in placed:
            v = vecs.get(r[0])
            if v is not None:
                scored.append((float(np.dot(v, vec)), r[1], r[2]))
        scored.sort(reverse=True)
        neighbours = scored[:8]

    weights = [max(s, 0.0) ** 2 for s, _, _ in neighbours]
    if not neighbours or sum(weights) == 0:
        a = rng.uniform(0, 2 * math.pi)
        r = 20 + 40 * rng.random()
        tx, ty = cx + r * math.cos(a), cy + r * math.sin(a)
    else:
        total = sum(weights)
        tx = sum(w * x for w, (_, x, _) in zip(weights, neighbours, strict=True)) / total
        ty = sum(w * y for w, (_, _, y) in zip(weights, neighbours, strict=True)) / total
        a = rng.uniform(0, 2 * math.pi)
        j = rng.uniform(6, 14)
        tx, ty = tx + j * math.cos(a), ty + j * math.sin(a)

    radius = 60 + 18 * math.sqrt(members)
    dist = math.dist((tx, ty), (cx, cy))
    if dist > radius:
        tx = cx + (tx - cx) * radius / dist
        ty = cy + (ty - cy) * radius / dist

    x, y = tx, ty
    if not grid.free(x, y):
        for k in range(1, 41):
            r, theta = MIN_GAP * k, GOLDEN * k
            px, py = tx + r * math.cos(theta), ty + r * math.sin(theta)
            if grid.free(px, py):
                x, y = px, py
                break
        else:
            # Very crowded: keep spiralling outward until a free spot exists.
            k = 41
            while not grid.free(x, y):
                r, theta = MIN_GAP * k, GOLDEN * k
                x, y = tx + r * math.cos(theta), ty + r * math.sin(theta)
                k += 1
    grid.add(x, y)
    return x, y
