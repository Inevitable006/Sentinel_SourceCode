# T-04: Complete the remaining local workflows

Owner instruction, 2026-10-03: build the full project according to the plan. This expands the earlier single-milestone scope. Work on `phase1/security`, preserve existing changes, no pushes.

## Scope and permitted files

Backend/core/API/database, frontend screens and Electron integration, tests, local packaging tools and documentation. Security changes are limited to reviewed approvals, cancellation, workspace containment, encrypted backup, audit integrity and skill permissions needed by the roadmap. Preserve the PIN, egress and single-use-token boundaries. No machine-security changes. No new cloud services. Model/runtime downloads are setup operations; application traffic must use the existing egress guard.

## Order and acceptance

1. Repair chat concurrency/approval continuation and enforce confirmation after untrusted tool output.
2. Working memory/history/privacy screens, skill switches and emergency stop.
3. Encrypted plans, tasks, reminders and editable email/calendar drafts. Scheduling never silently authorizes a tool or sends a message.
4. Owner-approved workspace operations with preview, conflict detection and undo; encrypted backup/restore; audit integrity.
5. Portable runtime packaging and installation checks where the machine permits them.
6. Full regression, real local smoke and frontend validation. Report actual limitations per feature.

## External prerequisites

Phase 2 native speech is blocked by Windows Application Control. Voice identity needs explicit owner enrollment; Windows Hello requires supported hardware and enrollment. Provider integration needs owner accounts/consent. These must remain visibly unavailable until validated; no fabricated integrations or claims of full completion.

## Report

In progress. Source review found that the old chat receiver remains sequential and previous tests only check eventual cancellation; approval results are returned through HTTP without conversation continuation. Correct these with behavioral tests rather than preserving inaccurate completion claims.

### Resume checkpoint — 2026-10-17

- Resumed on `phase1/security` from clean commit `9a0668b` (Phase 10 coding pack). The paragraph above is historical; subsequent work is recorded in T-05 and `docs/CAPABILITIES.md`.
- Continued the coding workflow's honest-result handling: zero discovered tests and entirely skipped suites now return an error with actionable guidance. Suites with executed passing tests and some skips still succeed.
- Files changed: `backend/skills/code_assistant/__init__.py`, its pinned entry in `backend/skill-hashes.json`, `backend/tests/skills/test_code_assistant.py`, this report and the tracker.
- Added real contained-runner regression cases for no matches, all skipped, and mixed executed/skipped tests.
- Coding continuation: limited numbered code-read content to 8,000 characters plus a truncation notice identifying the line, below the existing runner cap so continuation guidance survives. Added cases for a single long line and many lines; existing small-file output remains covered. No dependencies or new modules.
- Continuation validation: all 10 coding-skill tests passed; final full `tools/check.ps1 -Only tests` returned zero (517 backend tests, 13 memory checks, 17 JavaScript checks, frontend build and Electron syntax checks). Initial new test labels exceeded Windows' environment-variable limit; short explicit case IDs fixed the test harness. The first 16,000-character limit lost its notice at the existing runner cap; the final 8,000-character limit is verified through the approval/tool execution path.
- Final validation: `515 passed in 28.46s`; memory acceptance `13/13 passed`; 17 JavaScript checks, frontend typecheck/build and both Electron syntax checks passed. `tools/check.ps1 -Only tests` returned success in the current PowerShell session; `git diff --check` passed. Evidence: `docs/runs/check_20261017_160402.txt`.
- Check-environment limitation: the initial sandbox run could not create temporary databases (`PermissionError: [WinError 5] Access is denied`). Outside that restriction, the earlier `check.bat` invocation returned failure even though every recorded child check exited zero (513 backend tests, before the added cases were collected). The direct PowerShell rerun on the finished changes passed with no recorded PowerShell errors. The batch-wrapper discrepancy has not been diagnosed or changed.
- Still outstanding: clean-machine installer validation, owner microphone/lock-sleep checks, and later Phase 10 research/writing packs. No new dependencies, downloads, commits or pushes.
