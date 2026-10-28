# HTTP API

For web and bot developers: every REST and SSE endpoint (blueprint Appendix B). `openapi.json` next to this file is exported by `make openapi`; CI fails when it is stale.

## Authentication

Every route except health, sign-in and the sandbox needs a session: the `moira_session` cookie (`HttpOnly; Secure; SameSite=Lax`) or `Authorization: Bearer <token>` (the Telegram Mini App, whose cross-site iframe blocks cookies). Every state-changing request must send `X-Moira: 1` (CSRF guard). Nothing accepts a user id or a memory path from the client: session → user → memory.

## Endpoints

| Method & path | Auth | Rate limit | Body → Response | Notes |
|---|---|---|---|---|
| `POST /api/auth/link` | none | 5/min IP | `{token}` → `204` + cookie | One-time login (§10.2) |
| `POST /api/auth/telegram` | none | 10/min IP | `{init_data}` → `{bearer, user}` | Mini App sign-in |
| `POST /api/auth/logout` | user | — | → `204` | |
| `POST /api/auth/logout-others` | user | — | → `204` | Ends all other sessions |
| `POST /api/sandbox` | none | 5/hour IP | → `201 {user}` + cookie | Sample memory copy (§11.4) |
| `GET /api/me` | user | — | → `{id, kind, display_name, tz, caps: {spent_today, cap_today}, version}` | |
| `PATCH /api/me` | user | — | `{tz}` → `{…}` | IANA name validated |
| `GET /api/sky?since=<cursor>` | user | 60/min | → sky payload (§7.7.4), plus `stars.title` and `stars.source` columns (Q-012) | |
| `GET /api/events` | user | 5 open streams | SSE: `filed {star}`, `updated {id}`, `removed {id}`, `hub {hub}`, `ping` every 25 s | Live updates |
| `GET /api/nuggets/{id}` | user | 120/min | → `Card` (Appendix N.4; the sections of §4.3.6) | |
| `POST /api/nuggets/{id}/opened` | user | 120/min | → `204` | Increments `open_count` |
| `GET /api/recent?cursor=&kind=&source=&hub=` | user | 60/min | → `{items[50], next_cursor}` | §4.3.9 |
| `POST /api/nuggets` | user | 30/min | `{text}` → `202 {id, status}` | Text/links capture |
| `POST /api/nuggets/media` | user | 10/min | multipart `images[]` (≤ 10) or `audio` (≤ 3 min), optional `text` → `202 {id}` | Media sniffed by magic bytes; images stripped at once; audio capped at 6 MB (Q-013) |
| `PATCH /api/nuggets/{id}` | user | 30/min | `{user_text}` → `{version}` | Edit (§7.10) |
| `POST /api/nuggets/{id}/forget` | user | 30/min | → `{undo_group_id, undo_until}` | §7.11 |
| `POST /api/nuggets/{id}/move` | user | 30/min | `{hub_id}` or `{new_hub_name}` → `{group_id}` | |
| `POST /api/nuggets/{id}/unlink` | user | 30/min | `{hub_id}` → `{group_id}` | |
| `POST /api/nuggets/{id}/restore` | user | 30/min | → `{group_id}` | Earlier → current |
| `POST /api/nuggets/{id}/split` | user | 10/min | `{parts: [[raw_event_ids…], …]}` → `{ids}` | |
| `POST /api/undo` | user | 30/min | `{group_id?}` → `{undone_group_id}` | Most recent group if empty |
| `GET /api/hubs` · `GET /api/hubs/{id}` | user | 60/min | → hubs list / hub with members, Now line, history | |
| `GET /api/search?q=` | user | 60/min | → instant results (top 12 with clue labels) | No AI |
| `POST /api/ask` | user | 10/min | `{question, conversation_id?}` → SSE (§8.5) | AI tiers |
| `POST /api/turns/{id}/feedback` | user | 30/min | `{value: "found" \| "not_it"}` → `204` | §12.5 |
| `POST /api/turns/{id}/save-instead` | user | 10/min | → `{nugget_id}` | Misread question |
| `GET /api/export` | user | 2/hour | → zip (JSONL + Markdown + SQLite copy) | Not for sandboxes |
| `POST /api/forget-everything` · `DELETE /api/forget-everything` | user | 2/hour | → `{scheduled_for}` / `204` | 24 h grace |
| `GET /api/health` | none | 60/min IP | → `{ok, version}` (owner: more fields) | §13.11 |
| `GET /api/admin/stats` | owner | 30/min | → metrics | §13.11 |
| `POST /share` | user (cookie) | 10/min | form `title, text, url, files[]` → `303 /?saved=<id>` | Android share target; checks `Origin` instead of `X-Moira` (Q-013) |

## Server-sent events

`POST /api/ask` streams, in order: `clues` → `lit` → `status` (before each AI call, always specific: "Looking through 40 memories from around 12 Oct") → `answer` → `done`. When the AI is unavailable or over budget, `error` (with `fallback_ids` from the instant tier) comes before the degraded `answer`. `GET /api/events` sends `filed`, `updated`, `removed`, `hub`, and `ping` every 25 seconds; at most 5 open streams per user.

## Errors

`{"error": {"code": "...", "message": "..."}}` with standard status codes: 401 not signed in, 403 forbidden or missing `X-Moira`, 404 gone, 422 invalid, 429 rate limited (with `Retry-After`), 503 AI unavailable.

## Rate limits

Per user unless marked IP, as in the table. Kept in process (one process, §5.2).
