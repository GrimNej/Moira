"""Open (and create on first use) each user's memory database; one connection per file."""

import sqlite3
from pathlib import Path

from moira.clock import Clock
from moira.db.connection import write_lock
from moira.memory.create import MemoryKind, create_memory


class Memories:
    def __init__(self, data_dir: Path, clock: Clock, *, embed_model: str, embed_dim: int) -> None:
        self.data_dir = data_dir
        self.clock = clock
        self.embed_model = embed_model
        self.embed_dim = embed_dim
        self._conns: dict[str, sqlite3.Connection] = {}

    def path(self, memory_path: str) -> Path:
        return self.data_dir / memory_path

    def open(self, memory_path: str, kind: MemoryKind = "user") -> sqlite3.Connection:
        conn = self._conns.get(memory_path)
        if conn is None:
            conn = create_memory(
                self.path(memory_path),
                kind=kind,
                now=self.clock.now_ms(),
                embed_model=self.embed_model,
                embed_dim=self.embed_dim,
            )
            self._conns[memory_path] = conn
        return conn

    def lock(self, memory_path: str):  # type: ignore[no-untyped-def]  # asyncio.Lock
        return write_lock(self.path(memory_path))

    def close(self, memory_path: str) -> None:
        conn = self._conns.pop(memory_path, None)
        if conn is not None:
            conn.close()

    def close_all(self) -> None:
        for key in list(self._conns):
            self.close(key)
