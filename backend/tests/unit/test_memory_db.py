"""T09: a new memory has the schema, the meta keys and the 10 shelves on the ring."""

import math
from pathlib import Path

import pytest

from moira.db.repos import hubs, nuggets, stars
from moira.domain.shelves import SHELVES
from moira.domain.text import contains_evidence, name_norm
from moira.memory.create import create_memory, get_meta

MEMORY_TABLES = {
    "meta",
    "nuggets",
    "raw_events",
    "nugget_versions",
    "exacts",
    "enrichments",
    "research",
    "people",
    "hubs",
    "hub_members",
    "hub_events",
    "nugget_people",
    "stars",
    "conversations",
    "turns",
}
VIRTUAL = {"nugget_fts", "nugget_tri", "hub_fts", "vec_nuggets", "vec_hubs"}


def test_new_memory_has_every_table_and_index(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert names >= MEMORY_TABLES
    assert names >= VIRTUAL
    assert get_meta(conn, "kind") == "user"
    assert get_meta(conn, "embed_dim") == "256"


def test_ten_shelves_on_the_ring_from_twelve_oclock(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    shelves = hubs.shelves(conn)
    assert [h.name for h in shelves] == list(SHELVES)
    first = shelves[0]
    assert first.x == pytest.approx(0.0, abs=1e-9)
    assert first.y == pytest.approx(-1100.0)
    for i, h in enumerate(shelves):
        assert math.hypot(h.x, h.y) == pytest.approx(1100.0)
        angle = math.degrees(math.atan2(h.x, -h.y)) % 360
        assert angle == pytest.approx(36.0 * i, abs=1e-6)
    # The second shelf is clockwise (to the right of 12 o'clock on screen).
    assert shelves[1].x > 0


def test_create_memory_is_idempotent(tmp_path: Path) -> None:
    create_memory(tmp_path / "m.db", kind="user", now=1).close()
    conn = create_memory(tmp_path / "m.db", kind="user", now=2)
    assert len(hubs.shelves(conn)) == 10


def test_star_positions_never_move(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    n = nuggets.insert(
        conn,
        public_id="n_aaaaaaaaaaaa",
        source="typed",
        user_text="hi",
        captured_at=1,
        captured_tz="UTC",
        now=1,
    )
    stars.insert(conn, n.id, 10.0, 20.0, now=1)
    stars.insert(conn, n.id, 99.0, 99.0, now=2)
    s = stars.get(conn, n.id)
    assert s is not None and (s.x, s.y) == (10.0, 20.0)


def test_versions_keep_the_raw_text(tmp_path: Path) -> None:
    conn = create_memory(tmp_path / "m.db", kind="user", now=1)
    n = nuggets.insert(
        conn,
        public_id="n_bbbbbbbbbbbb",
        source="typed",
        user_text="it was Guy",
        captured_at=1,
        captured_tz="UTC",
        now=1,
    )
    assert nuggets.add_version(conn, n.id, "it was Josh", "web_edit", now=5) == 2
    assert [r["user_text"] for r in nuggets.versions(conn, n.id)] == ["it was Guy"]


@pytest.mark.parametrize(
    ("raw", "norm"),
    [("Favorite fruits", "favorite fruit"), ("To-dos", "to dos"), ("Links & reads", "link read")],
)
def test_name_norm(raw: str, norm: str) -> None:
    assert name_norm(raw) == norm


def test_evidence_is_a_case_insensitive_substring() -> None:
    assert contains_evidence("My favorite fruit is now  BANANA", "fruit is now banana")
    assert not contains_evidence("my favorite fruit is apple", "banana")
    assert not contains_evidence("anything", "   ")
