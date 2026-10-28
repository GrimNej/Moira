# CLAUDE.md — Moira

@AGENTS.md

## Working with Claude Code here

- One task from blueprint Appendix M per session: the human types `/task T08`. Stop when its "Done when" passes.
  The human reviews and merges, then clears the session before the next task.
- Large tasks (T13, T23, T28, T30, T36, T42, T43, T47): write a short plan first and wait for approval.
- Every commit you make ends with the trailer `Assisted-by: Claude Code`.
- Ask before: spending API credits, changing a prompt, adding a dependency that is not in blueprint Appendix N,
  deploying, running anything on the server, or editing BLUEPRINT.md beyond a "Changed:" note.
- If the blueprint is unclear, stop and ask. Do not guess. Log the question in docs/OPEN_QUESTIONS.md.
- Never put real personal data, tokens or keys in code, tests, commits, logs or chat.
