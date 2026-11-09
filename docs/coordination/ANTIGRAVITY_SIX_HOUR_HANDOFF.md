# AntiGravity: six-hour independent work window

Owner requested this handoff on 2026-11-01 so Codex can stop and conserve allowance. Codex is not running in parallel during this window. Six hours is a maximum planning budget, not a requirement to keep generating code or a guarantee of full-roadmap completion. Finish early if the authorized work is complete. This document overrides older ownership/build restrictions only for the exact exceptions below; all other README/AGENTS rules remain.

## Start here (0–20 minutes)

Read AGENTS.md, README_ANTIGRAVITY.md, both status files, and the scoped cards referenced here. Inspect git status/diffs; preserve all staged and unstaged work. Stay on phase1/security. No resets, cleaning, staging, commits, pushes or dependency upgrades. Do not rebuild the entire project merely to rediscover a passing baseline.

Latest Codex backend result: 665 tests passed in 33.38s after T-16 activation. Four calculator tools now use contained Windows workers; other skills are not all isolated. Existing installer predates these changes. AntiGravity reports final A2 PIN corrections, 4 settings-retry tests, 6 readiness tests and frontend build passing; Codex has read that report but has not independently reviewed/rerun this latest patch. Start by confirming those files and running the focused settings/readiness checks once.

Record IN_PROGRESS, selected task, exact paths and actual usage (UNKNOWN if unavailable). Re-read coordination only at task boundaries. No continuous polling or waiting for Codex replies: Codex has stopped. For an ambiguity outside scope, record it, preserve working state and continue independent authorized items.

## Ownership during this window

AntiGravity retains all A1–A3 and A5–A7 paths listed in README. Additional, explicit temporary transfer from Codex:

- `backend/app/core/skill_broker.py` (new), `backend/tests/security/test_skill_broker.py` (new), `docs/tasks/T-17-broker-authority.md`: T-17 only.
- `tools/check.ps1`: only add a Node invocation for `frontend/tests/settings-*.test.mjs` beside the existing readiness tests, with Record-Result so failure propagates. Preserve every existing check. Do not refactor the script.
- New `docs/coordination/ANTIGRAVITY_SIX_HOUR_REPORT.md` and generated verification logs under `docs/runs/`.
- Run the existing combined verification script, normally Codex-owned, after declaring the build in ANTIGRAVITY_STATUS. Codex has no build running. Do not change installer/build manifests or overwrite the existing installer.

Do not edit SecureRunner, policy/token/vault/egress/file_ops, skill_router, pure_skill_worker, dependency manifests, shared frontend API helpers, Electron main/preload, skill pins or other Codex files. Read them for context. No broker activation or runtime hook registration in this window. Do not edit CODEX_STATUS or this plan; record proposals in your report. If another worker appears, stop overlapping edits until ownership is resolved.

## Work sequence and time boxes

### 1. A5: actual settings behavior checks (20–90 minutes)

Continue the standing A5 scope; reuse settings-retry.test.mjs. Add settings-status.test.mjs and at most one shared helper only if reused. Tests must execute actual component handlers through existing Node/TypeScript tooling, not copied logic. Cover pending/duplicate submissions, failed status replacing stale success, out-of-order/unmounted replies, Google credential import failure and voice save/preview error handling. Fix demonstrated issues only in owned settings components. Keep exact PIN strings, target backup names, confirmation behavior and read-only Google scope. Use synthetic fixtures, no account login/owner backup/microphone.

If the current tests already cover a behavior, do not duplicate them. Distinguish hook-adapter results from real browser/DOM verification. Record commands, actual counts and uncovered cases. Add the narrow tools/check.ps1 test invocation once tests exist and pass.

### 2. A6: bounded usability checks (90–130 minutes)

Use existing A6 ownership. Check keyboard operation, labels, visible focus, loading/error feedback and narrow layout. Actual browser inspection must use an isolated synthetic fixture/profile, not the owner's live data. If browser tooling is unavailable, report static-only verification and continue. Fix small observed defects; no styling overhaul, shared CSS refactor, new framework or dependency. Run affected tests and one frontend build after this batch, not after every small edit.

### 3. A7: owner guide and acceptance checklist (130–170 minutes)

Complete docs/USER_QUICKSTART.md and docs/OWNER_ACCEPTANCE.md. Verify labels and behavior against source. Distinguish automated evidence, manual checks and unsupported features. PIN freshness is five minutes since successful verification, not inactivity; preserve exact PIN entry. Document creation/backup tests create data and must be labelled accordingly. Restoring must be tested only in a separate profile/machine with synthetic data, never over the owner's active profile. Do not claim live Google consent, audio quality, clean-machine success or guaranteed memory zeroing.

### 4. T-17: parent broker authority only (170–290 minutes)

Read docs/coordination/SKILL_BROKER_DESIGN.md and T-17. Implement the bounded parent authority object and tests in the transferred files only. No transport, actual data adapter or runtime activation. Do not enlarge the scope to consume remaining time.

Bind immutable approved arguments, request identity, generation, deadline and one-operation budget. A trusted parent supplies the read adapter; a worker never selects arbitrary functions, paths, credentials or tools. Deny invalid fields, altered targets, duplicate/out-of-order sequence and expired/revoked requests before effects. Concurrent requests must invoke the adapter at most once. Do not hold a revocation lock across a potentially blocking adapter call: lock/cancel must remain responsive; check generation again before releasing its result. Bound input/output before unbounded allocation and suppress raw adapter exceptions.

Use synthetic adapters and a fake clock. Test zero calls on denial, immutable argument snapshots, concurrency, revocation during a blocked read, output bounds and safe exceptions. No real network, filesystem/vault reads or secrets in fixtures. Do not weaken existing tests. This is an authority primitive, not a completed broker or security guarantee. If implementation cannot be completed and verified within this box, document exact unfinished state; do not import it into production. Preserve the working application.

### 5. Stabilization and final verification (290–340 minutes)

Stop new features. Run focused tests for changed files first. Then run `tools/check.ps1 -Only tests` once: backend, isolated memory, frontend/typecheck, Electron syntax, JavaScript and the newly registered settings tests. Run from repository root in PowerShell with the existing environment. The script's tests use synthetic/temporary data; never substitute the real APPDATA profile to fix a failure. If environment permissions block test temp/process creation, use the agent's normal approval process; do not disable Windows protection. Record blocked checks honestly and continue unaffected checks.

Fix regressions caused by your owned changes and rerun relevant checks. An unrelated failure outside transferred paths is a documented blocker, not permission to edit security code. Do not label the checkpoint release-ready while essential checks fail. No installer rebuild/deployment in this window; existing installer is retained.

### 6. Handoff (340–360 minutes, or earlier if finished)

Update ANTIGRAVITY_STATUS, T-17 Report and ANTIGRAVITY_SIX_HOUR_REPORT.md. Include exact files, commands/counts/exit codes, known failures, tests not run, running processes, temporary artifact locations, and a short next-step list. Distinguish code complete from verified and runtime active from preparation-only. State whether the final combined suite passed. Report ownership retained until Codex resumes and explicitly accepts the handoff. Do not claim six hours elapsed unless measured.

## Budget and interruption rules

Check actual provider allowance at task boundaries; UNKNOWN is acceptable. At 80% stop large new work, at 90% stabilize/report, at 95% hand off. Reserve the final hour for verification and documentation even if earlier tasks overrun; drop later scope rather than rush. On interruption/model switch, write a checkpoint and stop the old worker before the new one edits. No automatic purchase or reset. Do not keep working just to fill the clock.

## Explicitly outside this window

Advanced voice/wake word/voice identity/Windows Hello/Piper (A4), broker transport/activation, migration of effectful skills, credential/provider setup, CPU/call sensor integration, dependency/model downloads, installer promotion and owner-only hardware/clean-machine checks. These are still real roadmap work; list them as remaining. The bounded queue above is intended to produce a stable, reviewable increment rather than a false claim of total completion.
