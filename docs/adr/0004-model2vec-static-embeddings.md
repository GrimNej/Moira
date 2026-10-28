# 0004. model2vec potion-retrieval-32M int8, 256 dims, instead of a transformer embedding model

Date: 2026-10-28
Status: Accepted

## Context

A transformer embedding model would not fit the 1 GB RAM budget alongside everything else, and CPU inference on 1/8 OCPU would be slow. A remote embedding API would cost credits and fail when the API is down.

## Decision

Use model2vec `minishlab/potion-retrieval-32M` loaded with `quantize_to="int8"` and `dimensionality=256`, producing L2-normalised float32 vectors. Load it once at startup from a local cache with `HF_HUB_OFFLINE=1`.

## Consequences

- Easier: About 60 MB RAM, very fast on CPU, no API cost.
- Harder: Roughly 82% of MiniLM retrieval quality; fused with lexical, time and source channels to compensate (ADR 0015).
- Harder: If `dimensionality=256` is not accepted, use `model.dim` and record it in `meta.embed_dim`.

Blueprint: §7.6.
