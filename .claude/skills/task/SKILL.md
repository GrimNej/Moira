---
name: task
description: Build one task from Appendix M of the Moira blueprint. Use only when the user types /task with a task ID.
disable-model-invocation: true
argument-hint: "[task ID, e.g. T08]"
---

Build task $ARGUMENTS of Moira.

1. Open docs/blueprint/BLUEPRINT.md and find the row for $ARGUMENTS in Appendix M. If no ID was given, use the
   "Next" line of the newest DEVLOG.md entry. Quote the row back in one line.
2. Check the Depends column: every listed task must be merged (DEVLOG.md and `git log --oneline`).
   If one is not, stop and say which.
3. Read blueprint §0–§3 if you have not in this session, then only the sections in the row's Read column and the
   appendices they link. Do not read the rest of the blueprint.
4. Create the branch `t<NN>-<short-name>` from an up-to-date main.
5. Build only the files in the Build column, plus their tests and the docs that §13.10 names.
   Write the tests first where the task or §3 (🧪) says so.
6. Run `make check` and `make test` (and `make test-web` and `make e2e` for web tasks). Fix until all pass.
   Never skip, weaken or delete a test to get green.
7. Commit in small Conventional Commits (§13.2), each ending with `Assisted-by: Claude Code`.
   Push the branch and open a pull request with the template if `gh` is available.
8. Check the "Done when" column literally and show the evidence: test names and output; for UI, screenshots
   at 1440 and 390 px saved under docs/media/.
9. Add a DEVLOG.md entry (§13.5 format) ending with "Next: T<next ID>". Put anything the blueprint did not
   answer in docs/OPEN_QUESTIONS.md.
10. Stop. Report in five lines or fewer: what was built, the Done-when evidence, open questions, the next task ID.
    Do not start the next task.
