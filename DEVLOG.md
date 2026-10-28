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

**Decisions**

- `docs/blueprint/` is excluded from markdownlint: it is a frozen planning document.
- Version shown by `/api/health` comes from a deployed `VERSION` file, else `git describe` (Q-003).
- Dependabot ignores major versions until after the hackathon (Appendix N pins the stack).
- A ruff banned-API rule forbids `datetime.now()` and `time.time()` outside `clock.py` (§13.7).

**Problems**

- `make` is not installed on the Windows dev machine; the Makefile targets were run as their underlying commands. CI runs them on Ubuntu.

**Commits** first commits on `main` · **Tag** none yet
**Next** T15
**Built with** Claude Code (T01–T14 from Appendix M); reviewed by the developer.
