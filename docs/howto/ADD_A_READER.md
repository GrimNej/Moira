# Add a link reader

For developers: how to add a new link reader (blueprint §7.3.2).

## Steps

1. Add `backend/src/moira/readers/<name>.py` with `async def read(canonical: str) -> ReaderResult`.
2. Return a `ReaderResult` with `method` (add a new value to the `research.method` CHECK list in a migration if needed), `status` (`ok`, `blocked`, `error`, `not_found`, `skipped`), `title`, `author`, `findings` (short plain text), `excerpt` (≤ 3,000 characters) and `sources` (`[{url, title}]`).
3. Route the platform to it in `readers/base.py:read_link` (and add its host to `capture/urls.py:SOURCE_HOSTS` if it needs its own `source`).
4. Map `401/403/429/451`, empty bodies and "enable JavaScript" pages to `status="blocked"`: blocked links go to web research.
5. Results are frozen into `research` rows at save time; a second nugget with the same canonical URL reuses the stored reading.

## SSRF rules

- A reader that fetches a **user-controlled host** must use `readers/ssrf.SafeFetcher`. It allows only http/https on ports 80/443 without credentials, rejects any address that is not globally routable (checked on every resolved address and every redirect hop), pins the connection to the checked IP with the original Host header and SNI, follows at most 3 redirects, stops at 2 MB and accepts only HTML or plain text.
- Readers for **fixed API hosts** (YouTube oEmbed, the GitHub API) may use plain `httpx` with timeouts: the user controls only a query parameter or a path.
- Walled platforms (Instagram, X, TikTok, Facebook, Threads, LinkedIn) make **no request** (ADR 0009). They are researched with web search instead.

## Tests

- Write the test first, with `respx` mocks: no real network in tests.
- For a `SafeFetcher` reader, pass a fake resolver (`SafeFetcher(resolve=...)`) and mock the pinned IP URL.
- Add the reader's blocked, error and success cases to `tests/unit/test_ssrf_readers.py`.
