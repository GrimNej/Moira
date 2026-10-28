# 0013. Standard mode for real data; contributor mode for synthetic data only

Date: 2026-10-28
Status: Accepted

## Context

Meta's contributor mode lets Meta train on content. The hackathon gives a fixed credit budget, and contributor mode is a way to stretch it.

## Decision

Real user data is only ever sent in Standard mode. Contributor-mode models are used only for synthetic demo data and evaluation runs on synthetic data.

## Consequences

- Easier: Real memories are never used for training.
- Harder: Real-data calls cost the full Standard price.

Blueprint: §2.3.
