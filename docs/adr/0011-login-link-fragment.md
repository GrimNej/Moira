# 0011. Login link via URL fragment + POST; Mini App via `initData`; no passwords

Date: 2026-10-28
Status: Accepted

## Context

Telegram link previews fetch URLs, which would consume a one-time login token. Telegram Web embeds Mini Apps in a cross-site iframe where cookies are blocked. Passwords add risk and friction.

## Decision

The bot's `/web` command sends a one-time button to `/login#t=<token>`. The token travels in the fragment, is consumed only by a JavaScript POST to `/api/auth/link`, works once and expires in 10 minutes; link previews are disabled. The Mini App POSTs `initData`, which is validated with aiogram's `safe_parse_webapp_init_data` and rejected after 24 hours, and receives a bearer token. Sessions are random 32-byte tokens stored hashed. No passwords exist.

## Consequences

- Easier: Previews cannot burn tokens; the web app keeps working once telegram.org is blocked.
- Harder: Two auth mechanisms (cookie and bearer) to support.

Blueprint: §10.2.
