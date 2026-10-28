# Devlog

For judges, the developer and coding agents: how Moira was built, session by session. Newest entry first. Times in Nepal time (NPT).

## 2026-10-28 (Wed) · D0 · session 1

**Done**

- T01 repository skeleton: folders of blueprint §5.5, licence, editor and git config, blueprint v1.2 and design prototype under `docs/`, `AGENTS.md`, `CLAUDE.md`, the `/task` command, top-level docs and every `docs/` stub of §13.3.

- T02 decision records: ADR template and ADRs 0001–0020 (blueprint §13.4), each with Context, Decision and Consequences.

- T03 backend skeleton: uv project (Python 3.12.13, SQLite 3.50.4 locally), FastAPI app factory, pydantic-settings config for every Appendix A variable, structlog, `SystemClock`/`FixedClock`, `ids.new`, typed errors, `GET /api/health`; 18 tests pass, ruff and mypy clean. `.env.example` and `CONFIG.md` generated from Appendix A.
- T04 web skeleton: Vite 5 + Preact + TypeScript strict, Appendix H tokens, the frame and the black sky window; Jost latin only (Q-005). Playwright checks the 1440 px column and window and the 390 px full-bleed sky; JS 5.4 KB gzipped.
- T05 quality gates: Makefile (Appendix N.3), pre-commit (ruff, mypy, prettier, eslint, gitleaks, conventional commits, large files, private keys), CI with backend, web, e2e, security and docs jobs, PR and issue templates, Dependabot. A commit message without a type is rejected locally (checked). Hypothesis found a float rounding bug in `clock.to_ms`; fixed with integer maths.
- T06 server and deploy files: Caddyfile and `moira.service` from §13.13, backup and DuckDNS units, idempotent `bootstrap_server.sh` and `firewall.sh`, `deploy.sh` (refuses a dirty tree or red CI, builds the web locally, release folders, migrations, symlink switch, smoke test with rollback, keeps 3 releases), DEPLOY.md. **Blocked:** the server does not exist yet, so the live deploy and the rollback test wait for the owner (D0 step 2).
- T07 API verification: `scripts/verify_api.py` with the checks `structured`, `image`, `search`, `asr`, `video`, `effort`, `tokens`. **Blocked:** no `MODEL_API_KEY` yet, so no Meta check has run; the local checks J13 (sqlite-vec, trigram) and J14 (model2vec 256 int8, +70 MB) pass and are recorded.
- T08–T09 database core and memory database: pragmas, sqlite-vec (numpy fallback when extensions cannot load), forward-only migrations with snapshots, repositories for system.db and the memory database, new memories with the 10 shelves on the ring. Q-007: the job claim keeps strict capture order.
- T10–T12 parsers, test first: secret masking S1–S8 (every Appendix E.1 example plus 35 more; property tests that no detected secret survives), URL canonicalization (33 cases, idempotence property), exact strings, and the Appendix F time grammar (every row of the test table at Mon 26 Oct 2026 21:00 NPT).
- T13 job queue and worker: lanes (file FIFO per user, media one at a time), debounce with the 90 s cap, backoff with jitter and Retry-After, dead jobs, stuck-job requeue, budget and outage reschedules that do not use an attempt (§9.10).
- T14 capture service: raw event first, question detection (Telegram only), grouping of a bare link or media with a caption while the file job is queued, dedupe by canonical URL or short-text hash (saved_count), exacts, the instant index (FTS, trigram, vector) and link, media and debounced file jobs. A deterministic hash embedder stands in for model2vec in tests.
- T15 instant search on raw text: FTS (every term quoted, so FTS operators are inert), trigram substrings for exact-looking tokens and phrases, normalized exact lookups, fused with RRF.
- T16 bot capture: private chats only (groups get one line and the bot leaves), text, links, photos (largest ≤ 20 MB), albums (one nugget, one reaction), voice, video (≤ 90 s), documents, forwards with origin, locations and contacts, edits as versions with a re-file job, the secret warning with a delete button. Reactions only, never 'Saved' texts.
- T17 sign-in: one-time login links in the URL fragment (10 minutes, once), Mini App initData validated with aiogram and rejected after 24 h, hashed sessions as an HttpOnly cookie or a bearer token, the X-Moira CSRF header, per-route rate limits with Retry-After, /api/me, /web. The lifespan now builds the services and starts the worker and the bot.
- T18 bot commands: /start (owner on first start, tester and judge invites stored hashed, judges expire), /help, /web, /timezone, /forget (last or replied; 10-minute Undo button; deletes the Telegram message within 48 h; hard delete job), /undo (reverts the last AI event group), /stats (owner), /export (link until T50), /ask. Undo replays recorded event states; forget repairs fact hubs.
- T19 AI client: Responses calls through the openai SDK with store=False on every request, strict structured output (Chat Completions behind STRUCTURED_TRANSPORT), web search, Files API video, multipart ASR; pre-flight budget caps; circuit breaker (5 failures in 2 min → open 120 s → half-open probe); one repair attempt; a ledger row per call; prompts 1.0.0 from §9.8 with front matter; FakeLLM for tests.
- T20 embeddings: model2vec (256 dims, int8) behind an Embedder protocol, a deterministic hash embedder for tests, sqlite-vec KNN with a numpy fallback; KNN returns the item itself first in both. RSS: +70 MB for the model (Windows dev machine; see EXTERNAL_API_NOTES #2).
- T21 link readers and SSRF guard, test first: every §7.3.3 case blocked (private, loopback, link-local, CGNAT, unique-local, multicast, reserved, IPv4-mapped, decimal/hex/octal forms, a domain resolving to 127.0.0.1, a redirect to 169.254.169.254); pinned IP with Host and SNI; 3 redirects; 2 MB; YouTube oEmbed, GitHub API (repo, README, blobs), page metadata and main text; walled platforms make no request.
- T22 filing context and validation: the §7.4.1 blocks built in code (candidate hubs by FTS, hub vectors and people named; shelves; similar nuggets; recent context; known people; escaped found content), the ENRICH call, and V1–V12 with one test each plus the refresh and edit_refile modes. Date strings come from domain/timefmt.py (principle 11).
- T25 sky placement and importance: hub centres around the most similar hub (24 angles, ≥ 220 apart), stars pulled toward similar stars in their primary hub with seeded jitter, kept inside the constellation, spaced ≥ 9 units with a 16-unit spatial hash and a golden-angle spiral; importance formula of §7.7.3. 5,000 synthetic stars place in ~5 s with no two closer than 9.
- T23 filing apply: enrichment, image text and its exacts, new hubs placed near the most similar hub, memberships, add/replace/remove/correct with Earlier and Corrected roles, person hubs linked to people (two Joshes stay two), hub events for every change, full re-index, the star placed once, a live filed event and the ✍ reaction. Job handlers for file (waits ≤ 3 min for readers), refresh, edit_refile and hard_delete. With FakeLLM: apple → banana → oranges gives the expected Now lines and roles; found content and injected instructions never change a fact; undo restores the exact previous state.
- T24 research: read_link job (frozen readings reused for the same canonical URL), walled or blocked links researched with web search before filing, verified in code by post id (else 'possible'), not_found retried at +1 and +7 days, a later success refreshes derived fields only. Tests never touch the network: the app fixture's reader returns 'blocked'.
- T26 first real filing run: contract test and 10 synthetic update sequences (data/eval/updates.jsonl) ready. **Blocked:** needs MODEL_API_KEY and 5 public reels; run `make contract` once the key exists (spends a few cents).
- T27 query parsing and fusion: lexicons, Parsed (terms, phrases, exacts, source, kinds, time, past, intent, follow-ups), the vector, hub and people channels, RRF, and the time (telescoping ×1.6, windows), source, kind, history and importance priors. The vague question 'insta link about AI, ~2 weeks ago?' ranks the reel first in an integration test.
- T28–T29 answer and deep tiers: candidates with precomputed local dates, sources and verified/possible labels; ANSWER; citation validation (an invented citation becomes 'not found' with the closest matches); turns stored; deep tier with PLAN, lookup re-retrieval, and §8.4 SQL for lists and counts (the count comes from SQL); 'the one before/after that'; degraded mode emits error with fallback ids.
- T30 POST /api/ask over SSE (clues, lit, status, answer, done; never buffered), degraded mode as an error event with fallback ids, Found it / Not it feedback and Save instead on turns.

**Decisions**

- `docs/blueprint/` is excluded from markdownlint: it is a frozen planning document.
- Version shown by `/api/health` comes from a deployed `VERSION` file, else `git describe` (Q-003).
- Dependabot ignores major versions until after the hackathon (Appendix N pins the stack).
- A ruff banned-API rule forbids `datetime.now()` and `time.time()` outside `clock.py` (§13.7).

**Problems**

- `make` is not installed on the Windows dev machine; the Makefile targets were run as their underlying commands. CI runs them on Ubuntu.

**Commits** first commits on `main` · **Tag** none yet
**Next** T31
**Built with** Claude Code (T01–T30 from Appendix M); reviewed by the developer.
