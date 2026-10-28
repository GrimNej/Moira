# External API notes

For anyone calling an external API: verified facts about Meta, Telegram, GitHub and YouTube, with date and evidence (blueprint Appendix J).

Format: `#N · date · topic · Tested with: … · Result: … · Evidence: … · Affects: §…`.

## How to run the Meta checks

From `backend/` with `MODEL_API_KEY` set (spends a few cents; synthetic inputs only):

```bash
uv run python scripts/verify_api.py structured image search asr video effort tokens
```

Each check prints `#J<n> <check>: PASS|FAIL <evidence>`. Paste the lines below, then mark the Appendix J row.

## Status

| # | Check | Status |
|---|---|---|
| J1 | Official rules (Discord #questions) | Owner: ask on D0 |
| J2 | Credits expiry, contributor billing | Owner: Billing page on D0 |
| J3 | Structured output on Responses | **Blocked** until `MODEL_API_KEY` exists: `verify_api.py structured` |
| J4 | `input_image` data URL | **Blocked** (key): `verify_api.py image` |
| J5 | `web_search` options and billing | **Blocked** (key): `verify_api.py search` |
| J6 | ASR multipart schema | **Blocked** (key): `verify_api.py asr` |
| J7 | Files API for video | **Blocked** (key): `verify_api.py video` |
| J8 | Usage fields | Printed by every check above |
| J9 | Reasoning effort `minimal` | **Blocked** (key): `verify_api.py effort` |
| J10 | Rate limits | Console |
| J11 | Data handling, ZDR | Console |
| J12 | API key prefix | Owner: look at the key; S8 covers it meanwhile |
| J13 | sqlite extension loading, FTS5 trigram | Local ✅ (#1); server: check on deploy |
| J14 | model2vec 256 dims, int8 | Local ✅ (#2) |
| J15–J25 | Telegram, Mini App, OCI, Caddy, Safari | Need the bots, the server or phones (D1–D5) |

## Notes

- #1 · 2026-10-28 · SQLite extensions and trigram (J13) · Tested with: `sqlite3.enable_load_extension` + `sqlite_vec.load` + `CREATE VIRTUAL TABLE … USING fts5(x, tokenize='trigram')` on the dev machine (uv-managed CPython 3.12.13, Windows) · Result: SQLite 3.50.4, sqlite-vec v0.1.9 loads, trigram works · Evidence: `sqlite 3.50.4 vec v0.1.9 / trigram ok` · Affects: §6.1. The server (Ubuntu 24.04, SQLite 3.45) is checked on the first deploy.
- #2 · 2026-10-28 · model2vec dimensionality (J14) · Tested with: `StaticModel.from_pretrained("minishlab/potion-retrieval-32M", quantize_to="int8", dimensionality=256)` · Result: accepted; embedding matrix 63,091 × 256 int8; `encode` returns float32 vectors of 256 · Evidence: working set 203 MB with FastAPI + aiogram + openai imported, 273 MB after the model loaded (+70 MB, Windows) · Affects: §5.3, §7.6. Measure RSS on the server again (Linux counts less).
