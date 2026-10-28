# Open questions

For the developer and agents: anything the blueprint did not answer, the option picked, and its status.

Format: `Q-NNN · date · question · Picked: option · Status: open | answered (where)`.

## Questions

- Q-001 · 2026-10-28 · Appendix C files fail markdownlint as written (no blank lines around headings and lists; a bare URL). Copy verbatim or lint-clean? · Picked: lint-clean with formatting-only changes (blank lines, URL in backticks); wording unchanged. markdownlint rules MD036 (DEVLOG bold labels) and MD060 (`\|---\|` tables) are turned off because the blueprint prescribes those formats · Status: answered
- Q-002 · 2026-10-28 · §5.5 lists `Makefile`, `.env.example` and `.pre-commit-config.yaml` at the root, but T01's Build column does not. · Picked: create them in T03 (`.env.example`) and T05 (`Makefile`, pre-commit) as Appendix M says · Status: answered
- Q-003 · 2026-10-28 · §13.6 says `/api/health` returns `git describe`, but deploys rsync code without `.git`. · Picked: `config.app_version()` reads `backend/VERSION` when present (the deploy script writes it in T06), else `git describe --tags --always --dirty`, else the package version · Status: answered
- Q-004 · 2026-10-28 · Appendix N.1 gives no minimum for model2vec. · Picked: `model2vec>=0.4`; whether `dimensionality=256` with `quantize_to="int8"` works is checked in T20 (Appendix J14) · Status: open
