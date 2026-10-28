# 0017. Undo instead of confirmations

Date: 2026-10-28
Status: Accepted

## Context

Confirmations slow capture down and people click through them anyway (Raskin: "Never use a warning when you mean undo").

## Decision

Capture never asks. Every AI change to facts is recorded as hub events and can be undone; forgetting an item has a 10-minute undo window, and forgetting everything has a 24-hour grace period.

## Consequences

- Easier: Instant capture; mistakes are cheap.
- Harder: Every change must be recorded so it can be reverted.

Blueprint: §3.
