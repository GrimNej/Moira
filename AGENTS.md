# AGENTS.md — Moira

You are working on Moira: a personal memory you text like a friend (Telegram bot + web app),
drawn as a night sky. Full spec: docs/blueprint/BLUEPRINT.md. Read §0–§3 before any task.
Work from the task list in blueprint Appendix M: one task per session, only the sections it lists, stop when its
"Done when" passes. Exact packages, Makefile and tricky snippets: Appendix N.

## Commands (run from repo root)

- Setup: `make setup`            # uv sync (backend) + npm ci (web) + pre-commit install
- Run everything locally: `make dev`   # API+bot+worker on :8000 (FakeLLM unless MODEL_API_KEY set), Vite on :5173
- Backend tests: `make test`     # = cd backend && uv run pytest -m "not contract" -q
- One test: `cd backend && uv run pytest tests/unit/test_timeexpr.py -q -k weeks`
- Web tests: `make test-web`     # vitest run
- E2E: `make e2e`                # Playwright, phone + desktop, FakeLLM + seeded demo memory
- Lint/types: `make check`       # ruff check, ruff format --check, mypy, eslint, prettier --check, tsc --noEmit
- Eval: `make eval` (cached; costs ~nothing) · `make eval CONFIG=G`
- Contract tests (real Meta API, synthetic data only, costs credits): `make contract` — only when asked
- OpenAPI: `make openapi` · Demo template: `make demo-template` · Deploy: `make deploy` — only when asked

## Stack (exact)

Python 3.12 + uv · FastAPI · aiogram 3 · SQLite 3.45+ (WAL, FTS5, sqlite-vec) · model2vec potion-retrieval-32M int8 256d
· openai SDK → `https://api.meta.ai/v1` (Responses API) · pydantic v2 · structlog
Web: TypeScript strict · Preact + @preact/signals · Vite · Canvas 2D sky · Playwright · vitest
Type: Jost (display jobs only) + the system UI face. No UI kit, no CSS framework, no animation library.

## Structure

- backend/src/moira/{domain,capture,memory,search,ai,readers,media,jobs,bot,api,sandbox,backup,eval,db,embed}
- bot/ and api/ are thin: parse → call a service → format. No SQL outside db/repos/.
- ai/ is the only place that builds prompts. Prompts: backend/src/moira/ai/prompts/*.md (versioned front matter).
- web/src/{sky,components,state,api,lib,styles}
- Docs: docs/ (Diátaxis). Decisions: docs/adr/. Log: DEVLOG.md. Changes: CHANGELOG.md.

## Code style

- Type everything. pydantic models at every boundary. Typed errors from errors.py; no bare except.
- Time only via the injected Clock: never datetime.now() outside clock.py. Store UTC ms; show user tz.
- No print; use structlog. Never log user text, found content, prompts, outputs, URLs (host only) or emails.
- Small pure functions for parsing/scoring/placement. Example:

```python
def time_prior(t_ms: int, hint: TimeHint) -> float:
    diff = (t_ms - hint.target_ms) / DAY_MS
    sigma = hint.sigma_days * (1.6 if diff < 0 else 1.0)   # telescoping: widen the older side
    return max(0.04, math.exp(-0.5 * (diff / sigma) ** 2))
```

## Testing rules

- Write the test first for parsers, validators, security code and anything in §3 marked 🧪.
- Never call real external services in tests (FakeLLM, recorded fixtures, mocked Bot). Synthetic data only.
- Tests must pass before every commit. Add a regression test for every bug fixed.

## Git

- Conventional Commits: `feat(capture): …`, `fix(readers): …`, `docs(adr): …`, `test(memory): …`
- Small commits (one thing each), each green. Docs and tests in the same commit as the change.
- Footers: `Refs: #12`, `ADR: 0008`, `Assisted-by: Claude Code` (on every commit an AI tool wrote or co-wrote).
- Branch per task, PR with the template, rebase-merge. Never force-push main.
- After each task: update docs + DEVLOG entry (see Definition of Done, blueprint §13.10).

## Boundaries

Always:

- Follow the blueprint; if you must deviate, write an ADR and a "Changed:" note in BLUEPRINT.md.
- Keep the raw layer untouched by AI; mask secrets before storage and before any AI call.
- Validate every AI output against its schema; only user_text can change facts (evidence substring).
- Add anything the blueprint doesn't answer to docs/OPEN_QUESTIONS.md and choose the safest option.
- For any UI change: follow docs/design/DESIGN_RULES.md (blueprint §4.3.11) and attach phone + desktop screenshots.
- Send store=False on every Meta Responses call.
Ask first:

- Adding a dependency · changing a DB schema or a 🧪 principle's code · changing a prompt (needs eval)
- Running contract tests, eval with real models, deploy, or anything that spends API credits
- Deleting or rewriting docs/adr, DEVLOG, RESULTS, CHANGELOG history
Never:

- Commit secrets, tokens, .env files, real personal data, or real user memories (fixtures are synthetic)
- Use contributor-mode models on real data · scrape content behind logins · store media files
- Let found content (web pages, screenshots, research, video) change a fact
- Compute dates in prompts · log content · disable tests to make CI pass · force-push main
- Add glass/blur, gradients on chrome, monospace, tracked capitals, or any hue outside the data (stars, timeline, dots)
