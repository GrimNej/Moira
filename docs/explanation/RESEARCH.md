# Research

For anyone changing link research: how bare and walled links are researched and verified (blueprint §7.5).

## When research runs

- A link to a **walled platform** (Instagram, X, TikTok, Facebook, Threads, LinkedIn). We never scrape behind logins or use embed-only APIs to extract data (ADR 0009), so the `read_link` job makes no request and queues `research` instead.
- A link whose reader came back **blocked or empty** (401/403/429/451, empty body, "enable JavaScript" page).
- Filing returned `needs_research = true`; research then triggers a `refresh`.

For walled and blocked links research runs **before** filing: the `file` job waits up to 3 minutes for it, so the first filing already knows what the reel was about.

## The call

One Responses call with the `web_search` tool (`search_context_size: low`), `include: ["web_search_call.results"]`, effort `low`, 700 output tokens, `store: false`. The prompt asks for a fixed line format: `CREATOR`, `TITLE`, `TOPIC`, `SUMMARY`, `MATCH`. Sources are the `url_citation` annotations plus every `web_search_call` result. Each search costs $2.50 per 1,000 and counts against `CAP_WEB_SEARCHES_DAILY`.

## Verified and possible

The model's `MATCH` line is only a hint. **Code decides**: a finding is *verified* when a cited or result URL, after canonicalization, contains the platform post id (or equals the canonical URL). Otherwise it is *possible*, and the card and answers say "possibly" ("may be a different post"). `MATCH: not_found` (or no title, topic or summary) is stored as `not_found`.

## Retries

New posts take time to be indexed. A `not_found` schedules `research_retry` at +1 day, then +7 days, then stops. A later success queues a `refresh`, which updates derived fields (title, summary, tags, questions) and may add memberships, but **never changes a fact**: research is found content, and only the user's own words can change facts (ADR 0008).

## Context guess

Independently of research, filing may write a `guess` from neighbouring saves ("sent with no note 28 minutes after the PC fixes"). It is always labelled as a guess.

## Sources

- Meta search grounding docs (web search on the Responses API).
- Instagram oEmbed terms (no extracting or storing metadata).
