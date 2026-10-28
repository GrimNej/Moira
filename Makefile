.PHONY: setup dev test test-web e2e check eval contract openapi demo-template deploy
setup:            ## install everything
	cd backend && uv sync
	cd web && npm ci
	pre-commit install --hook-type pre-commit --hook-type commit-msg
dev:              ## API + bot + worker on :8000 (FakeLLM without MODEL_API_KEY), Vite on :5173
	trap 'kill 0' EXIT; \
	(cd backend && APP_ENV=dev uv run uvicorn moira.main:app --reload --port 8000) & \
	(cd web && npm run dev) & wait
test:             ## backend tests, no real API
	cd backend && uv run pytest -m "not contract" -q
test-web:
	cd web && npx vitest run
e2e:              ## Playwright, phone + desktop, FakeLLM + seeded demo memory
	cd web && npx playwright test
check:            ## lint, format, types
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src
	cd web && npx eslint . && npx prettier --check . && npx tsc --noEmit
eval:             ## cached evaluation; CONFIG=A..H, default all
	cd backend && uv run python -m moira.eval run --config $${CONFIG:-all} --cache .eval-cache
contract:         ## REAL API, synthetic data only, spends credits; only when asked
	cd backend && RECORD=$${RECORD:-0} uv run pytest -m contract -q
openapi:
	cd backend && uv run python -m moira.api.export_openapi ../docs/reference/openapi.json
demo-template:
	cd backend && uv run python scripts/build_demo_db.py --out $${DATA_DIR:-../.data}/templates/demo.db
deploy:           ## only when asked; refuses a dirty tree or a red CI
	./deploy/scripts/deploy.sh
