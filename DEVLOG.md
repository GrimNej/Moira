# Devlog

For judges, the developer and coding agents: how Moira was built, session by session. Newest entry first. Times in Nepal time (NPT).

## 2026-10-28 (Wed) · D0 · session 1

**Done**

- T01 repository skeleton: folders of blueprint §5.5, licence, editor and git config, blueprint v1.2 and design prototype under `docs/`, `AGENTS.md`, `CLAUDE.md`, the `/task` command, top-level docs and every `docs/` stub of §13.3.

- T02 decision records: ADR template and ADRs 0001–0020 (blueprint §13.4), each with Context, Decision and Consequences.

- T03 backend skeleton: uv project (Python 3.12.13, SQLite 3.50.4 locally), FastAPI app factory, pydantic-settings config for every Appendix A variable, structlog, `SystemClock`/`FixedClock`, `ids.new`, typed errors, `GET /api/health`; 18 tests pass, ruff and mypy clean. `.env.example` and `CONFIG.md` generated from Appendix A.

**Decisions**

- `docs/blueprint/` is excluded from markdownlint: it is a frozen planning document.
- Version shown by `/api/health` comes from a deployed `VERSION` file, else `git describe` (Q-003).
- A ruff banned-API rule forbids `datetime.now()` and `time.time()` outside `clock.py` (§13.7).

**Problems**

- None.

**Commits** first commits on `main` · **Tag** none yet
**Next** T04
**Built with** Claude Code (T01–T03 from Appendix M); reviewed by the developer.
