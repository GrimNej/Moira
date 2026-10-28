# 0005. Own web app is the main product; Telegram bot for capture; long polling

Date: 2026-10-28
Status: Accepted

## Context

The owner is in Nepal, where Telegram is blocked on mobile data but usually works on Wi-Fi. Telegram is still the fastest capture channel (share sheets, voice notes, forwards).

## Decision

The web app (PWA) is the main product: the sky, Ask, Recent, the composer and settings, usable without Telegram. The Telegram bot is a capture channel plus quick questions, and the same web app opens inside Telegram as a Mini App. The bot uses long polling, so Telegram needs no inbound port. Login does not depend on telegram.org scripts.

## Consequences

- Easier: Works where Telegram is blocked.
- Easier: No webhook endpoint to secure.
- Harder: Two surfaces to keep consistent.
- Harder: Only one poller per bot token; development uses a separate dev bot.

Blueprint: §4.1.
