# Security

For anyone reviewing Moira's security or reporting a problem.

## Reporting a problem

Please do not open a public issue for a security problem. Use GitHub's private vulnerability reporting on this repository ("Security" tab → "Report a vulnerability"). You will get a reply within 72 hours during the hackathon.

## Threat model, checked

The full table is [blueprint §10.1](docs/blueprint/BLUEPRINT.md). Each row was checked against
the code during the security pass (task T51, 2026-10-28). "Where" names the code and the tests
that hold the line.

| Threat | Mitigation | Where | Checked |
|---|---|---|---|
| Strangers spend credits through the public bot | Invite codes (stored hashed); unknown users get only the sample-memory link; caps per user kind and global, checked before every AI call | `accounts.py`, `bot/handlers_capture.py` (`WELCOME_PUBLIC`), `ai/usage.py`; `test_bot_commands`, `test_sandbox` (cap) | ✅ |
| Prompt injection via found content | Found content is quoted data in its own block; only `user_text` can change facts (V5 evidence substring); answers must cite real candidates | `memory/validate.py` V5, `search/ask.py` citation check; `test_filing` (injection case), `data/eval/updates.jsonl` | ✅ |
| SSRF through links | Every hop resolved and checked (private, loopback, link-local incl. 169.254.169.254, metadata), redirects followed by hand (max 3), no env proxies | `readers/ssrf.py`; `test_ssrf_readers` | ✅ |
| Secrets saved by accident | Masked before storage and before any AI call (typed text, transcripts, image text); nightly audit counts anything unmasked | `capture/secrets.py`, `capture/service.py`, `pipelines.py`, `memory/validate.py`, `jobs/maintenance.py`; `test_secrets` | ✅ |
| XSS from saved or fetched text | Preact text nodes only (no `dangerouslySetInnerHTML` anywhere); strict CSP in Caddy; only `http(s)` URLs become links | `web/src` (grep), `deploy/caddy/Caddyfile`, `web/src/lib/format.ts` `linkPieces`; `web/tests/links.test.ts` | ✅ (link rendering added in T51) |
| CSRF on cookie sessions | `SameSite=Lax` cookie; `X-Moira: 1` required on every state-changing `/api` route; `/share` (cannot send headers) checks `Origin` instead (Q-013) | `api/deps.py` `csrf`, every router; `api/routes_share.py`; `test_api_media` | ✅ |
| Login link consumed by link previews | Token in the URL fragment, consumed by a JavaScript POST; previews disabled; single use; 10 minutes | `web/src/components/Login.tsx`, `bot/handlers_commands.py` (`NO_PREVIEW`), `api/auth.py`; `test_auth` | ✅ |
| Forged Mini App login | `safe_parse_webapp_init_data`; `auth_date` older than 24 h rejected | `api/auth.py`; `test_auth` | ✅ |
| Session theft | 32-byte random tokens stored as SHA-256; `HttpOnly; Secure; SameSite=Lax`; rolling lifetime; "Sign out other sessions" | `api/auth.py`, `api/routes_auth.py` | ✅ |
| Malicious uploads | Caddy 25 MB body cap; per-type app limits; magic-byte sniffing; Pillow pixel cap (40 MP); images re-encoded without metadata; ffmpeg pinned to the sniffed demuxer with `-protocol_whitelist file`; generated names; argument lists only; timeouts; temp files deleted on any error | `api/uploads.py`, `media/{sniff,images,audio}.py`; `test_api_media`, `test_audio_safety` | ✅ (ffmpeg pinning added in T51) |
| SQL / FTS injection | Parameterized queries; SQL only in `db/repos/` (ruff S608 elsewhere); FTS terms quoted, operators inert | `db/repos/*`, `search/fts.py`; `test_instant_raw` | ✅ |
| Abuse / DoS | Rate limits per Appendix B; body limits; one media job at a time; sandbox creation per IP per hour; at most 200 sandboxes | `api/ratelimit.py`, `db/repos/jobs.py` (media lane), `sandbox/service.py` | ✅ |
| Data loss | Nightly encrypted off-server backups with retention; weekly export to the owner's Telegram; restore script and drill | `backup/backup.py`, `deploy/scripts/{backup,restore,restore_drill}.sh`, `docs/howto/RESTORE.md` | ✅ code · ☐ drill (needs the server) |
| Server compromise | SSH keys only, no root login; unattended upgrades; unprivileged `moira` user; systemd sandboxing; data dir `0700`; env file `0600` | `deploy/scripts/bootstrap_server.sh`, `deploy/systemd/*` | ✅ code · ☐ live check (needs the server) |
| Leaked tokens in git | gitleaks in pre-commit and CI; `.env` ignored; fake secrets in tests are joined at runtime | `.pre-commit-config.yaml`, `.github/workflows/ci.yml` | ✅ |
| Vulnerable dependencies | Lock files; `pip-audit` and `npm audit --omit=dev` in CI; Dependabot weekly | `.github/workflows/ci.yml`, `.github/dependabot.yml` | ✅ |

## What Moira keeps

The text of what you send (secrets hidden first), what it read from attachments, and what it
found about links. Images, audio and video are read into text and deleted. Nothing is used to
train models: requests go to Meta's Standard mode with `store=false`. You can export everything
or forget everything (24-hour grace) from Settings.
