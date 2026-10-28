# Configuration

For anyone running Moira: every environment variable (blueprint Appendix A). CI checks this file, `.env.example` and `config.py` list the same variables.

Local values go in `backend/.env` (git-ignored; start from `.env.example`). Production values go in `/etc/moira/env` (`root:root`, `0600`). The app refuses to start when a required variable is missing and names it.

## Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `APP_ENV` | yes | `dev` | `dev`, `test` or `prod`. `test` forces FakeLLM and `FixedClock` hooks. |
| `PUBLIC_BASE_URL` | yes | — | e.g. `https://moira.duckdns.org`; used in links, Mini App URLs, CSP checks |
| `DATA_DIR` | yes | `/var/lib/moira` | Root of all databases (§5.7) |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` only in dev with synthetic data |
| `DEFAULT_TZ` | no | `Asia/Kathmandu` | Time zone for new users |
| `TELEGRAM_BOT_TOKEN` | yes | — | Production or dev bot token (never the same token in two places) |
| `TELEGRAM_BOT_USERNAME` | yes | — | Without `@`; used for deep links |
| `OWNER_TELEGRAM_ID` | yes | — | Numeric id of the owner; gets digests, alerts, `/stats` |
| `MODEL_API_KEY` | yes (prod) | — | Meta Model API key |
| `MODEL_API_BASE` | no | `https://api.meta.ai/v1` | Meta API base URL |
| `MODEL_MAIN` | no | `muse-spark-1.3` | Standard-mode model for real data |
| `MODEL_CONTRIB` | no | `muse-spark-1.3-contributor` | Synthetic demo data and eval only |
| `MODEL_ASR` | no | `muse-voice-transcribe-1.0` | Transcription model |
| `STRUCTURED_TRANSPORT` | no | `responses` | `responses` or `chat` (§9.2) |
| `AI_ENABLED` | no | `true` | Kill switch: `false` = degraded mode everywhere, capture continues |
| `EMBED_MODEL` | no | `minishlab/potion-retrieval-32M` | model2vec model id |
| `EMBED_DIM` | no | `256` | Vector dimension (must match `meta.embed_dim`) |
| `EMBED_QUANTIZE` | no | `int8` | model2vec `quantize_to` |
| `HF_HOME` | no | `$DATA_DIR/models` | Model cache location |
| `HF_HUB_OFFLINE` | no | `1` in prod | Never download at startup |
| `CAP_GLOBAL_DAILY_USD` | no | `3.00` | §9.6 |
| `CAP_OWNER_DAILY_USD` | no | `1.50` | §9.6 |
| `CAP_TESTER_DAILY_USD` | no | `0.30` | §9.6 |
| `CAP_JUDGE_DAILY_USD` | no | `0.40` | §9.6 |
| `CAP_SANDBOX_DAILY_USD` | no | `0.10` | §9.6 |
| `CAP_WEB_SEARCHES_DAILY` | no | `150` | §9.6 |
| `CAP_VIDEO_DAILY` | no | `10` | §9.6 |
| `CAP_TOTAL_USD` | no | `120` | §9.6 lifetime |
| `WORKER_CONCURRENCY` | no | `3` | §7.0 |
| `SANDBOX_TTL_HOURS` | no | `24` | §11.4 |
| `SANDBOX_MAX_ACTIVE` | no | `200` | §11.4 |
| `SANDBOX_CREATE_PER_IP_HOUR` | no | `5` | §10.1 |
| `JUDGE_ACCESS_UNTIL` | no | `2026-11-20` | Judge accounts expire after this date (the community vote ends 16 Nov) |
| `SESSION_DAYS` | no | `90` | Rolling session lifetime |
| `LOGIN_TOKEN_MINUTES` | no | `10` | Login link lifetime |
| `GITHUB_TOKEN` | no | — | Fine-grained token, no scopes; raises GitHub rate limits |
| `DIGEST_LOCAL_TIME` | no | `08:00` | Owner digest time (owner's time zone) |
| `NIGHTLY_LOCAL_TIME` | no | `03:30` | Nightly job time per memory (user's time zone) |
| `BACKUP_AGE_RECIPIENT` | yes (prod) | — | `age1…` public key (backup script) |
| `BACKUP_RCLONE_REMOTE` | yes (prod) | — | e.g. `oci:moira-backups` (backup script) |
| `BACKUP_KEEP_DAILY` | no | `14` | Retention |
| `BACKUP_KEEP_WEEKLY` | no | `8` | Retention |
| `DUCKDNS_DOMAIN`, `DUCKDNS_TOKEN` | prod | — | Used only by the DuckDNS timer (`/etc/moira/duckdns.env`) |
| `MOIRA_HOST` | prod | — | Hostname for Caddy (systemd drop-in for `caddy.service`) |

`MODEL_API_KEY` is optional in dev: without it the app uses FakeLLM. `DUCKDNS_*` and `MOIRA_HOST` are read by the DuckDNS timer and Caddy, not by the app.
