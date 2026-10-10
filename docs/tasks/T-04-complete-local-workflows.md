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
