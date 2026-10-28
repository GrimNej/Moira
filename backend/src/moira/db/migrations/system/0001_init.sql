-- system.db schema v1 (blueprint §6.2). Accounts, sessions, jobs, usage ledger.

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);   -- keys: schema_version, last_backup_at, last_backup_bytes

CREATE TABLE users (
  id            INTEGER PRIMARY KEY,
  public_id     TEXT NOT NULL UNIQUE,
  kind          TEXT NOT NULL CHECK (kind IN ('owner','tester','judge','sandbox')),
  telegram_id   INTEGER UNIQUE,                  -- NULL for web-only sandboxes
  display_name  TEXT NOT NULL DEFAULT '',
  memory_path   TEXT NOT NULL,                   -- relative to DATA_DIR
  tz            TEXT NOT NULL DEFAULT 'Asia/Kathmandu',
  created_at    INTEGER NOT NULL,
  expires_at    INTEGER,                         -- sandboxes and judges
  disabled      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sessions (
  id_hash       TEXT PRIMARY KEY,                -- sha256 of the cookie value
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at    INTEGER NOT NULL,
  last_seen_at  INTEGER NOT NULL,
  expires_at    INTEGER NOT NULL,                -- rolling 90 days; sandboxes 24 h
  via           TEXT NOT NULL CHECK (via IN ('login_link','mini_app','sandbox'))
);
CREATE INDEX sessions_user ON sessions(user_id);

CREATE TABLE login_tokens (
  token_hash    TEXT PRIMARY KEY,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at    INTEGER NOT NULL,                -- 10 minutes
  used_at       INTEGER
);

CREATE TABLE invites (
  code_hash     TEXT PRIMARY KEY,
  role          TEXT NOT NULL CHECK (role IN ('tester','judge')),
  max_uses      INTEGER NOT NULL,
  uses          INTEGER NOT NULL DEFAULT 0,
  expires_at    INTEGER NOT NULL
);

CREATE TABLE jobs (
  id            INTEGER PRIMARY KEY,
  user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,                   -- see §7.0 job kinds
  ref           TEXT,                            -- usually a nugget public_id
  payload       TEXT NOT NULL DEFAULT '{}',      -- JSON
  lane          TEXT NOT NULL DEFAULT 'default', -- 'file' lanes are FIFO per user (see §7.0)
  status        TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed','dead','cancelled')),
  attempts      INTEGER NOT NULL DEFAULT 0,
  max_attempts  INTEGER NOT NULL DEFAULT 5,
  run_after     INTEGER NOT NULL,
  locked_at     INTEGER,
  last_error    TEXT,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
CREATE INDEX jobs_ready ON jobs(status, run_after);
CREATE INDEX jobs_ref ON jobs(user_id, ref);

CREATE TABLE usage_ledger (
  id              INTEGER PRIMARY KEY,
  user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
  day_utc         TEXT NOT NULL,                 -- YYYY-MM-DD
  kind            TEXT NOT NULL,                 -- enrich|research|answer|plan|tidy|video|asr|demo_gen|eval
  model           TEXT NOT NULL,
  input_tokens    INTEGER NOT NULL DEFAULT 0,
  cached_tokens   INTEGER NOT NULL DEFAULT 0,
  output_tokens   INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens INTEGER NOT NULL DEFAULT 0,
  web_searches    INTEGER NOT NULL DEFAULT 0,
  audio_seconds   INTEGER NOT NULL DEFAULT 0,
  est_usd         REAL NOT NULL,
  prompt_version  TEXT,
  latency_ms      INTEGER,
  ok              INTEGER NOT NULL,
  created_at      INTEGER NOT NULL
);
CREATE INDEX usage_day ON usage_ledger(day_utc, user_id);

CREATE TABLE telegram_chats (
  chat_id           INTEGER PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  last_message_at   INTEGER,
  last_nugget_pid   TEXT,                        -- for capture grouping
  last_export_at    INTEGER
);
