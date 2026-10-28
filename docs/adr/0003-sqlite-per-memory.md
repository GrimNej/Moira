# 0003. One SQLite file per memory; WAL; FTS5 (porter + trigram); sqlite-vec

Date: 2026-10-28
Status: Accepted

## Context

The server has tiny RAM and no budget for a database service. Each person's memory should be portable for life: copyable, openable with any tool, exportable.

## Decision

Use stdlib `sqlite3` (3.45+): a `system.db` for accounts, sessions, jobs and usage, and one memory database file per user, sandbox and template. Every connection uses WAL and the pragmas of §6.1. Full-text search uses FTS5 with a porter tokenizer plus a trigram index for substrings; vector KNN uses sqlite-vec, with a numpy brute-force fallback if extensions cannot load. One write lock per file.

## Consequences

- Easier: Zero ops, tiny RAM, one-file export and backup.
- Easier: Sandboxes are file copies.
- Harder: Single writer per file; writes are serialised.
- Harder: sqlite-vec loading depends on the Python build (VERIFY, Appendix J).

Blueprint: §5, §6.
