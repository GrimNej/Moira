# 0014. Budget caps with pre-flight estimates; degraded mode instead of failure

Date: 2026-10-28
Status: Accepted

## Context

Credits are fixed at $150. A public bot, testers, judges and sandboxes could overspend, and Meta's API can fail.

## Decision

Enforce daily caps per user kind and globally, plus a lifetime cap, in `ai/usage.py`. Every call is estimated before it is made; if it could exceed a cap it raises `AiBudgetExceeded`. A circuit breaker opens after repeated transient failures. In both cases the product degrades: capture keeps working and search falls back to instant, non-AI results.

## Consequences

- Easier: Overspending is impossible; outages never lose data.
- Harder: Answers can be weaker on busy days.

Blueprint: §9.6, §8.8.
