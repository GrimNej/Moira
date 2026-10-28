# Data model

For anyone touching the database: tables, columns and invariants (blueprint §6). The SQL files are the source of truth; this page explains them.

## Conventions

- Times are integers: milliseconds since the epoch, UTC. Only `moira.clock` reads the wall clock.
- Public ids are a prefix plus 12 URL-safe characters (`n_` nugget, `h_` hub, `p_` person, `u_` user, `s_` sandbox, `c_` conversation). Internal integer ids never leave the server.
- JSON columns (`tags`, `questions`, `sources`, `aliases`, `payload`, `media_meta`) are validated by pydantic models before writing.
- All SQL lives in `backend/src/moira/db/repos/` and is parameterized.
- Every connection sets the §6.1 pragmas (WAL, `synchronous=NORMAL`, foreign keys, 5 s busy timeout, memory temp store, 16 MB cache) and loads sqlite-vec when it can. Without sqlite-vec, the `vec_*` tables are plain `(rowid, embedding BLOB)` tables and search uses the numpy fallback.
- One write lock per database file (`db.connection.write_lock`).

## system.db

`backend/src/moira/db/migrations/system/0001_init.sql`

| Table | Holds |
|---|---|
| `meta` | `schema_version`, `last_backup_at`, `last_backup_bytes` |
| `users` | owner, testers, judges and sandbox visitors; each points at one memory file |
| `sessions` | hashed session tokens, rolling 90 days (sandboxes 24 h) |
| `login_tokens` | hashed one-time login tokens, 10 minutes |
| `invites` | hashed invite codes with role, uses and expiry |
| `jobs` | the job queue (§7.0); lanes `default`, `file`, `media` |
| `usage_ledger` | one row per AI call with tokens, searches, audio seconds and estimated cost |
| `telegram_chats` | chat → user, last message, last nugget (for grouping), last export |

## Memory database

`backend/src/moira/db/migrations/memory/0001_init.sql`. One file per user, sandbox or template.

| Layer | Tables |
|---|---|
| Raw (never edited by AI) | `nuggets` (`user_text`, `content_text`, URL, times, status), `raw_events`, `nugget_versions`, `exacts` |
| Derived (rebuildable) | `enrichments`, `research`, `people`, `hubs`, `hub_members`, `hub_events`, `nugget_people`, `stars` |
| Conversation | `conversations`, `turns` |
| Search indexes | `nugget_fts` (porter), `nugget_tri` (trigram), `hub_fts`, `vec_nuggets`, `vec_hubs` (256-dim float vectors) |

A new memory (`memory/create.py`) gets `meta` keys `created_at`, `kind`, `embed_model`, `embed_dim`, `layout_version`, and the 10 shelves on a ring of radius 1,100, clockwise from 12 o'clock in the §1.6 order.

## Invariants

1. Every non-deleted filed nugget has at least one hub membership and exactly one primary.
2. A fact or person hub's Now line comes only from members with role `current`.
3. Fact roles set by the AI carry evidence that is a case-insensitive substring of the nugget's `user_text` (`domain.text.contains_evidence`).
4. `nuggets.user_text` changes only through `nugget_versions` (`repos.nuggets.add_version`). Joining parts of one capture group appends without a version.
5. No table holds an unmasked secret.
6. `stars.x/y` never change after insert (`repos.stars.insert` ignores a second insert).
7. FTS, trigram and vector rows exist for every non-deleted nugget (the nightly check repairs drift).

## Migrations

| Database | Version | File | Notes |
|---|---|---|---|
| system | 1 | `0001_init.sql` | §6.2 |
| memory | 1 | `0001_init.sql` | §6.3; `{embed_dim}` is filled in at migration time |

Migrations are forward-only and additive during the hackathon. `python -m moira.db.migrate --all` snapshots every existing file before migrating it.
