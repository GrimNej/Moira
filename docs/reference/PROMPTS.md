# Prompts

For anyone changing a prompt: the catalog of prompts with version, model, effort, schema and latest eval scores.

Prompts live in `backend/src/moira/ai/prompts/<name>.md` with front matter (`name`, `version`, `model`, `effort`, `schema`, `changelog`). The version is written to every `usage_ledger` row and every `enrichments` row. A prompt change bumps the version, runs the eval (blueprint §12) and records the scores here and in `docs/eval/RESULTS.md`, in its own commit.

Rules for every call: fixed instructions first and variable blocks last (prompt caching), variable content escaped (`<` → `‹`, `>` → `›`), `store: false`, structured output with `strict: true`.

| Prompt | Version | Model | Effort | Max output | Schema | Latest eval |
|---|---|---|---|---|---|---|
| `enrich` | 1.0.0 | muse-spark-1.3 | low | 1,500 | `EnrichOutput` | not run yet |
| `research` | 1.0.0 | muse-spark-1.3 + `web_search` | low | 700 | line format | not run yet |
| `answer` | 1.0.0 | muse-spark-1.3 | low | 700 | `AnswerOutput` | not run yet |
| `plan` | 1.0.0 | muse-spark-1.3 | minimal | 400 | `PlanOutput` | not run yet |
| `now` | 1.0.0 | muse-spark-1.3 | minimal | 150 | `NowOutput` | — |
| `tidy` | 1.0.0 | muse-spark-1.3 | medium | 1,200 | `TidyOutput` | — |
| `video` | 1.0.0 | muse-spark-1.3 (Files API) | low | 4,000 | line format | — |
| `demo_gen` | 1.0.0 | muse-spark-1.3-contributor | low | 4,000 | `DemoGenOutput` | synthetic data only |

## Testing

- `FakeLLM` (`ai/fake.py`) gives deterministic, rule-based outputs so the pipeline runs offline and in CI.
- Contract tests (`make contract`, real API, synthetic inputs, spends credits) run only when asked.
