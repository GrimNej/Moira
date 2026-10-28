# 0012. Per-visitor sandboxes with time rebasing

Date: 2026-10-28
Status: Accepted

## Context

Judges and visitors need to try the product instantly, on any judging day, without seeing anyone's real memory, and phrases like "two weeks ago" must stay true.

## Decision

"Try the sample memory" copies the built template database for each visitor with the SQLite backup API and shifts every time column by `now − template_now − 2 h`. A test asserts every `*_at`, `since` and `until` column is rebased. Sandboxes expire after 24 hours; at most 200 are active.

## Consequences

- Easier: An instant, private, realistic demo on any day.
- Harder: Every new time column must be added to the rebase list (the coverage test enforces it).

Blueprint: §11.4.
