"""T20: 256-float L2-normalized vectors; KNN returns the item itself first (vec0 and numpy)."""

import os
import sqlite3

import numpy as np
import pytest

from moira.db import connection
from moira.embed.model import HashEmbedder, Model2VecEmbedder, load_embedder
from moira.search import vectors

TEXTS = [
    "five AI tools for video editing",
    "turn on XMP in the BIOS for faster RAM",
    "Josh's email is josh.r@example.com",
    "my favorite fruit is banana",
    "lofi playlist for focus",
]


def test_hash_embedder_shape_and_norm() -> None:
    m = HashEmbedder(256).encode(TEXTS)
    assert m.shape == (5, 256) and m.dtype == np.float32
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0, atol=1e-5)


def make_table(conn: sqlite3.Connection, use_vec: bool) -> None:
    if use_vec:
        conn.execute("CREATE VIRTUAL TABLE vec_nuggets USING vec0(embedding float[256])")
    else:
        conn.execute(
            "CREATE TABLE vec_nuggets (rowid INTEGER PRIMARY KEY, embedding BLOB NOT NULL)"
        )


@pytest.mark.parametrize("use_vec", [True, False])
def test_knn_returns_the_item_itself_first(monkeypatch: pytest.MonkeyPatch, use_vec: bool) -> None:
    if use_vec and not connection.vec_available():
        pytest.skip("sqlite-vec not available here")
    monkeypatch.setattr(connection, "_vec_state", use_vec)
    conn = connection.open_db(":memory:")
    make_table(conn, use_vec)
    emb = HashEmbedder(256)
    m = emb.encode(TEXTS)
    for i, vec in enumerate(m, start=1):
        vectors.upsert(conn, "vec_nuggets", i, vec)
    for i, vec in enumerate(m, start=1):
        hits = vectors.knn(conn, "vec_nuggets", vec, 3)
        assert hits[0][0] == i
        assert hits[0][1] == pytest.approx(1.0, abs=1e-4)


def test_upsert_replaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection, "_vec_state", False)
    conn = connection.open_db(":memory:")
    make_table(conn, False)
    emb = HashEmbedder(256)
    vectors.upsert(conn, "vec_nuggets", 1, emb.encode(["a"])[0])
    vectors.upsert(conn, "vec_nuggets", 1, emb.encode(["b"])[0])
    assert conn.execute("SELECT COUNT(*) FROM vec_nuggets").fetchone()[0] == 1
    got = vectors.get(conn, "vec_nuggets", 1)
    assert got is not None and np.allclose(got, emb.encode(["b"])[0])


def test_unknown_table_is_refused() -> None:
    conn = connection.open_db(":memory:")
    with pytest.raises(ValueError, match="table"):
        vectors.knn(conn, "nuggets; DROP TABLE x", np.zeros(256, dtype=np.float32), 1)


def test_load_embedder_fake_and_failure() -> None:
    assert isinstance(load_embedder("x", 256, "int8", fake=True), HashEmbedder)
    assert load_embedder("/nonexistent/model", 256, "int8", fake=False) is None


@pytest.mark.skipif(not os.environ.get("MOIRA_REAL_EMBED"), reason="set MOIRA_REAL_EMBED=1")
def test_real_model2vec() -> None:
    emb = Model2VecEmbedder("minishlab/potion-retrieval-32M", 256, "int8")
    m = emb.encode(TEXTS)
    assert m.shape == (5, 256)
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0, atol=1e-5)
    sims = m @ m[0]
    assert int(np.argmax(sims)) == 0
