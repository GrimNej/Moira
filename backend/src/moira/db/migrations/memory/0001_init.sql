-- Memory database schema v1 (blueprint §6.3). One file per user, sandbox or template.

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- keys: schema_version, created_at, kind (user|sandbox|template), embed_model, embed_dim, layout_version,
--       template_now (templates only, §11.3), forget_all_at (scheduled "forget everything", §7.11)

-- Raw layer --------------------------------------------------------------

CREATE TABLE nuggets (
  id                  INTEGER PRIMARY KEY,
  public_id           TEXT NOT NULL UNIQUE,
  source              TEXT NOT NULL CHECK (source IN
                        ('typed','voice','screenshot','instagram','youtube','github','web',
                         'x','tiktok','facebook','threads','video','forward','location','contact','other')),
  user_text           TEXT NOT NULL DEFAULT '',  -- the user's own words (typed or transcribed), secrets masked
  content_text        TEXT NOT NULL DEFAULT '',  -- text read from attachments (image text, video, PDF): NOT the user's words
  url                 TEXT,                      -- first URL as sent (masked)
  url_canonical       TEXT,
  captured_at         INTEGER NOT NULL,
  captured_tz         TEXT NOT NULL,
  original_posted_at  INTEGER,                   -- forwards
  forward_from        TEXT,
  status              TEXT NOT NULL DEFAULT 'raw' CHECK (status IN ('raw','reading','researching','filing','filed','failed')),
  version             INTEGER NOT NULL DEFAULT 1,
  dedupe_key          TEXT,                      -- canonical URL, or sha1 of normalized user_text for short texts
  saved_count         INTEGER NOT NULL DEFAULT 1,
  open_count          INTEGER NOT NULL DEFAULT 0,
  pinned              INTEGER NOT NULL DEFAULT 0,
  has_masked_secret   INTEGER NOT NULL DEFAULT 0,
  is_sample           INTEGER NOT NULL DEFAULT 0,
  deleted_at          INTEGER,                   -- soft delete (10-minute undo window)
  created_at          INTEGER NOT NULL,
  updated_at          INTEGER NOT NULL
);
CREATE INDEX nuggets_time   ON nuggets(captured_at);
CREATE INDEX nuggets_dedupe ON nuggets(dedupe_key);
CREATE INDEX nuggets_source ON nuggets(source, captured_at);

CREATE TABLE raw_events (                       -- every inbound message/request, before anything else
  id                INTEGER PRIMARY KEY,
  channel           TEXT NOT NULL CHECK (channel IN ('telegram','web','share','import','demo')),
  external_id       TEXT,                        -- 'chat_id:message_id' for Telegram
  kind              TEXT NOT NULL,               -- text|link|photo|album|voice|video|document|forward|location|contact|question|other
  text              TEXT,                        -- masked
  media_meta        TEXT,                        -- JSON: mime, bytes, duration_s, width, height, file_name (media itself is never kept)
  received_at       INTEGER NOT NULL,
  original_posted_at INTEGER,
  edit_of           INTEGER REFERENCES raw_events(id),
  nugget_id         INTEGER REFERENCES nuggets(id) ON DELETE CASCADE
);
CREATE INDEX raw_events_nugget ON raw_events(nugget_id);
CREATE UNIQUE INDEX raw_events_ext ON raw_events(channel, external_id) WHERE external_id IS NOT NULL AND edit_of IS NULL;

CREATE TABLE nugget_versions (
  id          INTEGER PRIMARY KEY,
  nugget_id   INTEGER NOT NULL REFERENCES nuggets(id) ON DELETE CASCADE,
  version     INTEGER NOT NULL,
  user_text   TEXT NOT NULL,
  edited_at   INTEGER NOT NULL,
  edited_via  TEXT NOT NULL CHECK (edited_via IN ('telegram_edit','web_edit'))
);

CREATE TABLE exacts (                           -- extracted by code, character for character
  id          INTEGER PRIMARY KEY,
  nugget_id   INTEGER NOT NULL REFERENCES nuggets(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL CHECK (kind IN ('url','email','phone','handle','hex_color','number','date_text','code')),
  value       TEXT NOT NULL,                     -- as written
  normalized  TEXT NOT NULL,                     -- lowercased/canonical form for matching
  origin      TEXT NOT NULL CHECK (origin IN ('user_text','content_text'))
);
CREATE INDEX exacts_lookup ON exacts(kind, normalized);

-- Derived layer ----------------------------------------------------------

CREATE TABLE enrichments (
  nugget_id        INTEGER PRIMARY KEY REFERENCES nuggets(id) ON DELETE CASCADE,
  title            TEXT NOT NULL,
  summary          TEXT NOT NULL,
  kind             TEXT NOT NULL CHECK (kind IN ('link','idea','fact','person','todo','note')),
  tags             TEXT NOT NULL DEFAULT '[]',   -- JSON array
  questions        TEXT NOT NULL DEFAULT '[]',   -- JSON array of search questions
  structured_list  TEXT,                         -- JSON {title, items[]} or NULL
  guess            TEXT NOT NULL DEFAULT '',
  model            TEXT NOT NULL,
  prompt_version   TEXT NOT NULL,
  raw_output       TEXT NOT NULL,                -- validated JSON, for audit and debugging
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);

CREATE TABLE research (
  id             INTEGER PRIMARY KEY,
  nugget_id      INTEGER NOT NULL REFERENCES nuggets(id) ON DELETE CASCADE,
  method         TEXT NOT NULL CHECK (method IN ('youtube_oembed','github_api','page_fetch','web_search','image','video','pdf','asr')),
  status         TEXT NOT NULL CHECK (status IN ('ok','not_found','blocked','error','skipped')),
  title          TEXT NOT NULL DEFAULT '',
  author         TEXT NOT NULL DEFAULT '',
  findings       TEXT NOT NULL DEFAULT '',       -- plain text; always shown as found content
  excerpt        TEXT NOT NULL DEFAULT '',       -- frozen page/README excerpt (≤ 3,000 chars)
  sources        TEXT NOT NULL DEFAULT '[]',     -- JSON [{url,title}]
  verified       INTEGER,                        -- 1 verified, 0 possible, NULL n/a
  searches       INTEGER NOT NULL DEFAULT 0,
  attempt        INTEGER NOT NULL DEFAULT 1,
  next_retry_at  INTEGER,
  created_at     INTEGER NOT NULL
);
CREATE INDEX research_nugget ON research(nugget_id);

CREATE TABLE people (
  id            INTEGER PRIMARY KEY,
  public_id     TEXT NOT NULL UNIQUE,
  display_name  TEXT NOT NULL,
  aliases       TEXT NOT NULL DEFAULT '[]',      -- JSON: ["Josh","Joshua","J"]
  disambiguator TEXT NOT NULL DEFAULT '',        -- e.g. "friend from school" vs "coworker"
  created_at    INTEGER NOT NULL
);

CREATE TABLE hubs (
  id           INTEGER PRIMARY KEY,
  public_id    TEXT NOT NULL UNIQUE,
  name         TEXT NOT NULL,
  name_norm    TEXT NOT NULL,                    -- lowercase, punctuation stripped, singularized
  kind         TEXT NOT NULL CHECK (kind IN ('shelf','topic','person','fact')),
  now_line     TEXT NOT NULL DEFAULT '',
  x            REAL NOT NULL,                    -- constellation center (world units)
  y            REAL NOT NULL,
  person_id    INTEGER REFERENCES people(id) ON DELETE SET NULL,
  archived     INTEGER NOT NULL DEFAULT 0,
  merged_into  INTEGER REFERENCES hubs(id),
  created_at   INTEGER NOT NULL,
  updated_at   INTEGER NOT NULL
);
CREATE UNIQUE INDEX hubs_name ON hubs(name_norm) WHERE archived = 0;

CREATE TABLE hub_members (
  hub_id      INTEGER NOT NULL REFERENCES hubs(id) ON DELETE CASCADE,
  nugget_id   INTEGER NOT NULL REFERENCES nuggets(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('member','current','earlier','corrected','related')),
  is_primary  INTEGER NOT NULL DEFAULT 0,        -- the hub that positions the star
  since       INTEGER NOT NULL,
  until       INTEGER,                           -- set when role becomes earlier/corrected
  decided_by  TEXT NOT NULL CHECK (decided_by IN ('ai','user','code')),
  confidence  REAL,
  evidence    TEXT NOT NULL DEFAULT '',          -- quote from user_text for fact roles
  PRIMARY KEY (hub_id, nugget_id)
);
CREATE INDEX hub_members_nugget ON hub_members(nugget_id);

CREATE TABLE hub_events (                       -- history + undo
  id          INTEGER PRIMARY KEY,
  group_id    TEXT NOT NULL,                     -- one filing or one user action
  hub_id      INTEGER REFERENCES hubs(id) ON DELETE SET NULL,
  nugget_id   INTEGER REFERENCES nuggets(id) ON DELETE SET NULL,
  event       TEXT NOT NULL CHECK (event IN ('hub_created','hub_renamed','hub_merged','member_added','member_removed',
                                             'role_changed','now_changed','moved','restored','forgotten','undone')),
  before_json TEXT,
  after_json  TEXT,
  actor       TEXT NOT NULL CHECK (actor IN ('ai','user','code')),
  undone      INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL
);
CREATE INDEX hub_events_group ON hub_events(group_id);

CREATE TABLE nugget_people (
  nugget_id  INTEGER NOT NULL REFERENCES nuggets(id) ON DELETE CASCADE,
  person_id  INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  PRIMARY KEY (nugget_id, person_id)
);

CREATE TABLE stars (                            -- stable positions
  nugget_id      INTEGER PRIMARY KEY REFERENCES nuggets(id) ON DELETE CASCADE,
  x              REAL NOT NULL,
  y              REAL NOT NULL,
  importance     REAL NOT NULL DEFAULT 0.5,      -- 0..1, recomputed nightly (§7.7.3)
  placed_at      INTEGER NOT NULL,
  layout_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE conversations (id INTEGER PRIMARY KEY, public_id TEXT UNIQUE NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE turns (
  id               INTEGER PRIMARY KEY,
  conversation_id  INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  question         TEXT NOT NULL,
  parsed           TEXT NOT NULL,                -- JSON from search/parse.py
  answer           TEXT NOT NULL,
  cited            TEXT NOT NULL DEFAULT '[]',   -- JSON public_ids
  confidence       TEXT NOT NULL,
  tier             TEXT NOT NULL CHECK (tier IN ('instant','answer','deep')),
  latency_ms       INTEGER NOT NULL,
  est_usd          REAL NOT NULL DEFAULT 0,
  feedback         TEXT CHECK (feedback IN ('found','not_it')),   -- "Found it / Not it" on answers
  created_at       INTEGER NOT NULL
);

-- Search indexes (maintained by code in memory/indexing.py, not by triggers) --

CREATE VIRTUAL TABLE nugget_fts USING fts5(
  title, summary, user_text, content_text, questions, tags, research, hub_names,
  tokenize = 'porter unicode61 remove_diacritics 2'
);                                               -- rowid = nuggets.id

CREATE VIRTUAL TABLE nugget_tri USING fts5(
  text, tokenize = 'trigram'
);                                               -- rowid = nuggets.id; user_text + content_text + exacts + url, for substring search

CREATE VIRTUAL TABLE hub_fts USING fts5(
  name, now_line, member_titles,
  tokenize = 'porter unicode61 remove_diacritics 2'
);                                               -- rowid = hubs.id

CREATE VIRTUAL TABLE vec_nuggets USING vec0(embedding float[{embed_dim}]);   -- rowid = nuggets.id, L2-normalized vectors
CREATE VIRTUAL TABLE vec_hubs    USING vec0(embedding float[{embed_dim}]);   -- rowid = hubs.id
