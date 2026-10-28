# 0009. Walled links are researched by web search, never scraped; verified/possible labels

Date: 2026-10-28
Status: Accepted

## Context

Instagram, X, Facebook, TikTok and LinkedIn put content behind logins, and Instagram's embed API forbids extracting or storing its metadata. A bare link with no note is unfindable later.

## Decision

Never scrape walled platforms or use embed-only APIs. Instead, research the link with Muse Spark's web search tool at save time. A finding is labelled *verified* only when a result URL contains the post id (checked in code), otherwise *possible*. A `not_found` result is retried after 1 and 7 days.

## Consequences

- Easier: Bare links become findable and survive deletion of the post.
- Easier: Respects platform terms.
- Harder: Some links stay unresearched; web searches cost credits (capped).

Blueprint: §7.5.
