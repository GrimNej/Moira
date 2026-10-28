# Devlog

For judges, the developer and coding agents: how Moira was built, session by session. Newest entry first. Times in Nepal time (NPT).

## 2026-10-28 (Wed) · D0 · session 1

**Done**

- T01 repository skeleton: folders of blueprint §5.5, licence, editor and git config, blueprint v1.2 and design prototype under `docs/`, `AGENTS.md`, `CLAUDE.md`, the `/task` command, top-level docs and every `docs/` stub of §13.3.

- T02 decision records: ADR template and ADRs 0001–0020 (blueprint §13.4), each with Context, Decision and Consequences.

- T03 backend skeleton: uv project (Python 3.12.13, SQLite 3.50.4 locally), FastAPI app factory, pydantic-settings config for every Appendix A variable, structlog, `SystemClock`/`FixedClock`, `ids.new`, typed errors, `GET /api/health`; 18 tests pass, ruff and mypy clean. `.env.example` and `CONFIG.md` generated from Appendix A.
- T04 web skeleton: Vite 5 + Preact + TypeScript strict, Appendix H tokens, the frame and the black sky window; Jost latin only (Q-005). Playwright checks the 1440 px column and window and the 390 px full-bleed sky; JS 5.4 KB gzipped.
- T05 quality gates: Makefile (Appendix N.3), pre-commit (ruff, mypy, prettier, eslint, gitleaks, conventional commits, large files, private keys), CI with backend, web, e2e, security and docs jobs, PR and issue templates, Dependabot. A commit message without a type is rejected locally (checked). Hypothesis found a float rounding bug in `clock.to_ms`; fixed with integer maths.

**Decisions**

- `docs/blueprint/` is excluded from markdownlint: it is a frozen planning document.
- Version shown by `/api/health` comes from a deployed `VERSION` file, else `git describe` (Q-003).
- A ruff banned-API rule forbids `datetime.now()` and `time.time()` outside `clock.py` (§13.7).

**Problems**

- `make` is not installed on the Windows dev machine; the Makefile targets were run as their underlying commands. CI runs them on Ubuntu.

**Commits** first commits on `main` · **Tag** none yet
**Next** T06
**Built with** Claude Code (T01–T05 from Appendix M); reviewed by the developer.
