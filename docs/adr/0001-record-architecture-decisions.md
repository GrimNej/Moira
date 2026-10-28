# 0001. Record architecture decisions

Date: 2026-10-28
Status: Accepted

## Context

Moira is built fast, mostly by a coding agent, and judged partly on its repository. Decisions made in the blueprint must stay visible and traceable when the code changes, and the "new work only" rule asks for an honest record of who decided what.

## Decision

Use Architecture Decision Records in Michael Nygard's format, one file per decision in `docs/adr/NNNN-kebab-title.md`, numbered in order and never deleted. A changed decision gets a new ADR that supersedes the old one. New ADRs are required for any change to a 🧪 principle's implementation, a new dependency, a schema change that alters an invariant, a model or API change, or anything that differs from the blueprint.

## Consequences

- Easier: Anyone (judge, agent, future developer) can see why the code is the way it is.
- Easier: Deviations from the blueprint are explicit.
- Harder: A little writing for every significant decision.

Blueprint: §13.4.
