# 0016. Conservative question detection; everything logged raw first

Date: 2026-10-28
Status: Accepted

## Context

In the Telegram chat, the same box is used to save and to ask. Treating a save as a question would lose data.

## Decision

A message is a question only if it ends with `?`, starts with `/ask`, or starts with a small set of question phrases, and has no URL or attachment. Everything else is saved. Every incoming message is written to the raw event log before anything else happens. Answers offer **Save instead**.

## Consequences

- Easier: Nothing can be lost by misclassification.
- Harder: Some questions without a question mark are saved; the user can use `/ask`.

Blueprint: §4.2.3.
