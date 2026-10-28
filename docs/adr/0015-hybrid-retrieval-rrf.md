# 0015. Hybrid retrieval with RRF, time/source priors, LLM answer tier

Date: 2026-10-28
Status: Accepted

## Context

People remember by context: roughly when, where it came from, what it was about. Pure vector search misses exact strings, pure keyword search misses meaning, and people misdate things in known ways.

## Decision

Parse the query in code (time phrases, sources, people, terms). Retrieve from several channels (FTS, trigram, exacts, vectors, hubs), fuse them with reciprocal rank fusion, and apply time and source priors (the older side widened ×1.6). An answer tier then asks Muse Spark to answer from the candidates with citations; a deep tier plans lists and counts.

## Consequences

- Easier: Finds things from vague memories; measured by the benchmark.
- Harder: More moving parts to tune.

Blueprint: §8.
