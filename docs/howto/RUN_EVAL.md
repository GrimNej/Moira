# Run the evaluation

For anyone changing prompts or search: how to run the benchmark (blueprint §12).

## Cached run (free)

```bash
make eval              # all configs A–H
make eval CONFIG=G     # one config
```

`python -m moira.eval run` builds the eval memory once from `data/demo/nuggets.jsonl` by running the real capture and filing pipeline (cached in `backend/.eval-cache/`), then runs `data/eval/queries.jsonl` with a FixedClock at Mon 26 Oct 2026, 21:00 Kathmandu time. Without `--real` it uses **FakeLLM** and the hash embedder: the numbers then check the pipeline, not model quality, and the results row says so.

Delete `backend/.eval-cache/` to rebuild the eval memory after changing the sample data or the filing code.

## Real-model run (spends credits; ask first)

```bash
cd backend && uv run python -m moira.eval run --config all --real
```

`--real` uses the contributor model (synthetic data only, ADR 0013). Every structured response is cached by (prompt name, prompt version, input hash), so a re-run with unchanged prompts costs almost nothing.

## Reading the results

Each run appends one row per config to `docs/eval/RESULTS.md` (never edit old rows) and redraws `docs/media/eval_recall_by_config.svg`.

| Config | Adds |
|---|---|
| A | FTS on the raw user text only |
| B | + enrichment fields (title, summary, tags) |
| C | + search questions and hub names (doc2query-style) |
| D | + vectors and the exact channel (hybrid RRF) |
| E | + hubs and people channels |
| F | + time and source priors |
| G | + the ANSWER tier (top citation, not-found precision) |
| H | + the deep tier |

Metrics: Recall@1, Recall@5 and MRR@10 of retrieval; the share of answers whose first citation is right; not-found precision on unanswerable questions; hallucinated citations after validation (must be 0); median seconds per question; dollars per question.
