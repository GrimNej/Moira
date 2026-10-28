# Search

For anyone changing retrieval: why search works the way it does (blueprint §8).

People rarely remember exact words. They remember *when*, *where it came from* and *roughly what it was about*. Search is built in three tiers: **instant** (no AI, ≤ 200 ms, also the fallback when AI is unavailable), **answer** (one ANSWER call over the top 40) and **deep** (PLAN, then SQL for lists and counts, or a second retrieval).

## Query parsing

`search/parse.py` (code only) turns the question into: terms (stopwords and memory filler removed), quoted phrases, exact tokens (emails, handles, colours, codes, URLs, numbers), a source ("insta", "reel" → Instagram), kinds ("email" → person), a time hint from the grammar of Appendix F, whether the question is about the past, the intent (lookup, list, count) and follow-ups ("the one before that"). The AI never computes dates.

## Channels and fusion

| Channel | What | Weight |
|---|---|---|
| FTS | `nugget_fts` with every term quoted (FTS operators are inert), bm25 with column weights | 1.0 |
| Vector | model2vec KNN on the terms and phrases | 1.0 |
| Exact | normalized exact lookups and trigram substrings (`#38BDF8`, `josh.r@`) | 2.0 |
| Hubs | top 5 hubs by FTS and hub vectors → their current and member items by importance | 0.6 |
| People | names or aliases in the question → that person's items | 1.5 |

Reciprocal rank fusion: `score(d) = Σ wᵢ / (60 + rankᵢ(d))`. RRF needs no score calibration across channels, which is why it is the standard way to fuse lexical and dense retrieval.

## Time and source priors

Multiplied after fusion:

- **Time:** a Gaussian around the remembered time. When the item is *older* than the remembered time the width is ×1.6, because people remember distant events as more recent (the telescoping effect). Inside an explicit window ("last week") the prior is 1.0; outside, the distance is measured to the nearest edge. Floor 0.04, so a misremembered date never hides the right answer completely.
- **Source:** ×1.7 for a match, ×0.2 otherwise (soft: people mix up apps).
- **Kind:** ×1.3 for a match.
- **History:** Earlier and Corrected items ×0.55, or ×1.2 when the question is about the past.
- **Importance:** ×(0.85 + 0.3 × importance).

A question that is only a time or a source ("what did I save yesterday?") falls back to scanning recent items by those priors.

## Answer tiers

See `search/ask.py`: the answer tier sends the top 40 candidates with their precomputed local dates; citations are validated in code, and an answer without a valid citation becomes "I couldn't find that" plus the closest matches (principle 10).

## Sources

- TREC Tip-of-the-Tongue track: hybrid retrieval beats any single method; an LLM reranker does best.
- Nogueira et al., doc2query: writing likely questions into each document at index time.
- Janssen et al. (2006), memory for time; the telescoping effect.
- Dumais et al., Stuff I've Seen: time and people are strong re-finding cues.
