# Task cards (for Antigravity / Codex)

Claude writes one card per delegated task: `docs/tasks/T-<nn>-<short-name>.md`.
Only low-risk work goes here (UI, docs, refactors covered by tests, cleanup). Security-critical code stays with Claude (see `AGENTS.md`).

**How to run a card:** open the repo in Antigravity and say:

> Read AGENTS.md and docs/tasks/T-<nn>-<name>.md, then do the task. Stop and ask if anything is unclear.

When it's finished, tell Claude "T-<nn> done". Claude reviews the diff and the test results.

## Card template
- **Goal:** one or two sentences.
- **Branch:** e.g. `phase1/security`
- **Files you may change:** …
- **Do not change:** …
- **Steps:** numbered and concrete.
- **Acceptance:** exact checks (tests to add, command to run, expected result).
- **Report (agent fills in):** files changed · test result line · open questions.
