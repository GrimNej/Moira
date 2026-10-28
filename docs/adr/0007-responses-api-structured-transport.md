# 0007. All Muse Spark calls on the Responses API; `STRUCTURED_TRANSPORT` switch

Date: 2026-10-28
Status: Accepted

## Context

Meta's web search tool is available on the Responses API but not on Chat Completions. Structured output is supported on both, with different request shapes.

## Decision

Every Muse Spark call goes through the Responses API with the `openai` SDK pointed at `https://api.meta.ai/v1`, sending `store: false` on every call. Structured output uses `text.format` with `strict: true`. A config switch `STRUCTURED_TRANSPORT=responses|chat` lets the structured calls move to Chat Completions without touching callers if the Responses path misbehaves.

## Consequences

- Easier: One client for search, structured output and video.
- Easier: A fallback if a Responses detail differs from the docs.
- Harder: Field names not printed on Meta's page must be confirmed by a contract test (Appendix J3).

Blueprint: §9.2.
