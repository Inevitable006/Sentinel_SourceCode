# Codex status

This file belongs to Codex. AntiGravity reads it but does not overwrite it.

- Task: T-19 bounded broker message framing
- State: ACCEPTED — bounded T-19 framing complete; live pipe transport remains unfinished
- Last updated: 2026-11-02
- Reserved paths: backend/**, tools/**, shared APIs, package/build files and coordination documents. Previous temporary T-17/check.ps1 transfer has ended; AntiGravity owns its A8/A9 queue only in addition to existing frontend paths.
- Build running: no; frontend build is free
- Usage checkpoint (2026-11-01, account snapshot): 82% of five-hour window used, 30% of weekly window used. Design-only checkpoint; no large implementation started. Check usage before T-17 implementation; follow README section 8.
- Current API: READINESS_API.md version 1 implemented; 640 backend tests passed in 29.13s, exit 0
- Latest verified checkpoint: 627 backend tests, 13 memory checks, 18 JS checks, frontend build; real encrypted semantic smoke passes in development and packaged runtimes; installer build exit 0
- Known remaining work: advanced voice/identity, full skill isolation, call/CPU thermal sensing and live provider/hardware/clean-machine acceptance
- Requests for AntiGravity: follow the standing queue in README: A2 final corrections → A5 behavior tests → A6 usability → A7 acceptance guide. Proceed after each report without waiting for a new prompt. A4 remains WAITING.
- Integration rule: Codex reviews AntiGravity-owned files read-only and requests corrections here; no concurrent edits

## Completed task reports

Coordination setup: created README_ANTIGRAVITY.md, READINESS_API.md and separate status files. No application behavior changed. The owner will start AntiGravity; this file does not imply that another agent is running.

Budget coordination: added staged 80/90/95% thresholds, safe checkpoint/handoff requirements and same-owner model-switch rules to README section 8. No running checks or unfinished runtime edits introduced by this documentation task. C1 remains the next implementation task.

C1 active paths: backend/app/core/readiness.py, backend/app/workspace_routes.py, backend/tests/integration/test_readiness.py, docs/tasks/T-13-readiness-backend.md. Backend-only checks planned; frontend build is free for AntiGravity.

C1 implementation available now: GET /api/workspace/readiness follows version 1 with all six checks. Focused tests passed before the final regression run; final backend-only result pending. AntiGravity may integrate its UI without changing the contract. Native recognizer status() is deliberately not called because it loads a model; unknown is returned until a prior runtime check exists. Voice initialization and Google network access are never triggered by readiness.

## C1 completion and A1 review — 2026-10-31

C1 final backend regression: **640 passed in 29.13s**, exit 0. No checks running. Existing installer predates C1/A1; rebuild after integration is accepted. Earlier pending notes above are historical.

A1 reviewed read-only; AntiGravity retains all frontend ownership. Reported frontend build passed; UI interaction evidence is still needed. Please fix these bounded issues in ReadinessPanel.tsx:

1. Reject malformed known entries rather than retaining positive badges: duplicate IDs, empty label/detail and oversized arrays currently pass through slicing/filtering, and unknown IDs can render Ready. Enforce the v1 contract before rendering; omit unknown future IDs or fail safely. An invalid payload must clear checks and show a recoverable error. Exercise duplicates, empty strings, invalid types and more than six entries with synthetic data.
2. Use a request generation counter (invalidated on cleanup) or equivalent cancellation guard. The shared isMounted boolean becomes true again during React StrictMode effect replay (enabled in main.tsx), allowing an older request to overwrite a newer result or clear its loading state. Exercise two deferred responses resolved out of order, including an older success after a newer lock/error response, plus unmount.

After these corrections, report the focused results and frontend build; then proceed to A2/A3. Codex will review the updated files and perform combined release checks after frontend changes settle. No API changes requested.

## A1 follow-up acceptance — 2026-11-01

Read-only review confirms strict v1 validation and generation checks on success, failure, finally and cleanup. Both requested corrections are accepted at code-review level. AntiGravity reports 12 validation and 2 cancellation simulations plus a passing build; Codex has not independently reproduced those simulations. Live Electron integration remains unverified. A2 and A3 are cleared now; no need to wait for C2 release validation.

AntiGravity next steps:
1. Record A2 IN_PROGRESS and inspect only GoogleSettings.tsx, VoiceSettings.tsx and BackupSettings.tsx. Fix observed duplicate submissions, stale results, missing pending/error handling or accessibility gaps. Preserve PIN, confirmations, read-only Google scopes and existing endpoints. If no defect exists, report NO_CHANGE_NEEDED.
2. Exercise changed interactions with synthetic data, record reproducible commands and results, and build once after the bounded changes. Announce build ownership first. Do not use owner accounts, recordings or backup files for tests.
3. Record A2 completion, then write docs/USER_QUICKSTART.md (A3), checking actual labels in source. Cover PIN/recovery, typed chat, approvals, document search, dictation review, optional Google connection, backup/restore and stop/lock/offline. Link existing setup documents. Distinguish implemented, verified and owner-only acceptance.
4. Update ANTIGRAVITY_STATUS with exact files, checks, unresolved issues and next step. After A3 report QUEUE_EXHAUSTED; A4 stays blocked on the voice backend contract. Do not invent additional features.

Codex retains backend, shared contracts and final integration/package checks. Avoid another full backend run or installer build until changes justify it. Current installer still predates C1/A1. Budget policy: bounded changes with a test/handoff checkpoint each time; no large new work at 80%, stabilization at 90%, handoff at 95% of the most-used reported window. These thresholds are checkpoints, not guaranteed automatic cutoffs.

## T-14 component verification — 2026-11-01

Codex added tools/tests/readiness.test.mjs and its tools/check.ps1 invocation. Actual TSX validator and component request logic are exercised with controlled hook/API adapters. All 6 readiness checks pass; combined existing JavaScript checks total 24 passed, 0 failed. No frontend edits or build outputs touched. No processes left running. Backend unchanged (last result 640 passed).

AntiGravity: A2/A3 remain cleared; the new regression check is available via `node --test tools/tests/readiness.test.mjs` from repository root. Keep your frontend build coordination. Remaining C2 requires A2/A3 reports, real rendering/IPC checks and the final installer refresh; component adapters do not establish those results.

## A2/A3 review corrections — 2026-11-01

AntiGravity retains ownership; please resume the existing tasks (no new feature scope):

1. **BackupSettings PIN retry dispatches the wrong operation.** The added form always calls create(). If Save a copy receives pin_required, Confirm PIN creates another backup instead of downloading the selected backup. Retain the exact pending operation/name and retry it after PIN entry; Cancel clears it. Verify create and download PIN retries separately, including cancellation. Do not change backend PIN rules.
2. **Read/load races remain in A2.** Backup and Voice use isMountedRef, which becomes true during StrictMode replay. Apply request-generation guards to initial/read refreshes so a late response cannot replace newer state. Clear stale backup data after a load failure, and distinguish a failed listing from an actually empty list. Use bounded corrections rather than more formatting.
3. **Quickstart factual corrections.** DocumentSearch.tsx has `Prepare next document` (one per click), not `Prepare meaning search for all unindexed documents`. Match that behavior. Do not call the software egress guard a hardware-style firewall, claim guaranteed key zeroing, or say remote writes are permanently disabled (currently unsupported is accurate). Explain fresh-PIN reuse for five minutes rather than implying every action prompts. Verify remaining labels and remove unsupported guarantees. A3 is not accepted yet.

Codex preparing T-15 independently while these corrections are pending. The pure-calculation worker is not connected to SkillRouter; no runtime isolation claim or installer promotion yet. Existing working installer preserved.

T-15 preparation checkpoint: bounded worker and 13 tests implemented; full backend suite **653 passed**, exit 0, 2026-11-01. No running tests/processes. Runtime routing remains unchanged. Added files: backend/app/core/pure_skill_worker.py, backend/tests/security/test_pure_skill_worker.py, docs/tasks/T-15-pure-skill-worker.md. Next: AntiGravity applies the A2/A3 corrections, then Codex completes C2 integration and scopes worker activation with approval/cancellation/lock regression tests. No request for additional features or A4 activation.

Owner relayed AntiGravity's original A2/A3 completion report; current code still contains the reviewed PIN dispatch defect. The report predates the corrections and does not resolve them. AntiGravity's next READY work is the A2/A3 corrections above, not A4.

Independent T-15 follow-up: 16 focused worker tests pass (1.14s), including real request cancellation, process untracking and both truncated/over-budget output refusal. No runtime edits or new dependencies in this increment. No tests/processes left running. Full backend checkpoint remains 653 passed before these three added tests; do not claim a new full-suite count until run.

Latest T-15 checkpoint: **21 focused tests passed in 1.48s**. Bounded source reads before allocation and rejected invalid identifier types; real Windows child tests also verify refused network/backend imports and the existing memory limit. No processes left running. AntiGravity's next action remains the A2/A3 correction list above; its old QUEUE_EXHAUSTED status does not mean those review findings are resolved. Worker activation and release promotion remain gated on C2.

## A2 final review — 2026-11-01

New report reviewed against files: pending operation dispatch, load generation guards and original guide corrections are present. Two bounded corrections remain:
- BackupSettings.handlePinSubmit passes pin.trim(), altering valid PINs with surrounding spaces (vault/setup preserve exact strings). Submit the original pin and do not reject valid all-space strings through a trim-based emptiness check. Backend remains authoritative for validity.
- USER_QUICKSTART says five minutes of inactivity; vault.pin_fresh measures elapsed time since successful PIN verification. Correct the description.

AntiGravity may add frontend/tests/settings-retry.test.mjs under the new README task to exercise actual component handlers, including exact PIN preservation, create/save retry, Cancel and stale load handling. Existing reported test_a2_corrections.mjs was not found in repository file inventory, so retain a reproducible check rather than reporting only an ephemeral simulation. No new dependency. A4 stays WAITING. Codex is running combined checks; no concurrent frontend build.

Combined verification completed successfully: tools/check.ps1 -Only tests exit 0 (2026-11-01). Includes backend, isolated memory checks, frontend typecheck/build, Electron syntax and JavaScript tests. No processes left running; AntiGravity may build now. Remaining review findings above still apply: passing existing tests does not prove exact-PIN retry behavior. Installer promotion waits for those fixes. Usage snapshot: 53% five-hour, 25% weekly; keep the next step bounded.

## Standing parallel plan — owner instruction 2026-11-01

README now authorizes A2 final fixes, A5 reproducible settings checks, A6 bounded usability verification and A7 owner acceptance guide. Exact paths and completion checks are included. AntiGravity proceeds at task boundaries without new prompts; only dependent features such as A4 wait for backend contracts. Codex owns C3 worker activation/broker design, C4 voice backend/contract and C5 system/release validation. C3 backend progress is decoupled from frontend review; activation requires a new scoped task and policy/lock/cancellation tests. Existing T-15 worker is still inactive. Final installer waits for both lanes; do not bypass known defects to call the project complete. No build currently running.

T-16 now activates the four calculation tools in SkillRouter, before parent module load/capability injection. Existing SecureRunner approval/limits/audit unchanged. Worker tracks lock generation, cancels active request processes and refuses locked/late results. Focused activation + worker + calculator checks: 52 passed in 3.72s. Full backend regression running. AntiGravity's queue/APIs unchanged; prior inactive-worker notes are historical.

T-16 final checkpoint: **665 backend tests passed in 33.38s**, exit 0. Worker activation is complete for four calculation tools only; no installer rebuild or general broker claim. No running tests/processes. Next backend work is the approved-effect broker design and its scoped task, after checking remaining usage. AntiGravity continues A2 final corrections → A5 → A6 → A7 independently. Release integration awaits both lanes. Existing installer remains unchanged and predates these changes.

T-17 design checkpoint: added SKILL_BROKER_DESIGN.md and docs/tasks/T-17-broker-authority.md. Inspected parent approval, file-preview/conflict and egress contexts and current memory callback injection. Document tool's empty capability list is not sufficient authority; explicit per-tool operation mappings are required. Next task is bounded parent authority/deny-by-default dispatch with synthetic tests, no runtime activation. No code/tests/build output changed; 665-test T-16 checkpoint remains the latest backend verification. No running processes. AntiGravity queue unchanged.

Owner requested Codex stop and transfer a six-hour work plan. ANTIGRAVITY_SIX_HOUR_HANDOFF.md is the active plan: A5/A6/A7, T-17 authority-only implementation, combined verification and final report. Codex explicitly releases the listed T-17 files and narrow check.ps1 edit; AntiGravity may run combined checks while Codex is stopped. No running processes or builds. The latest A2 exact-PIN patch/test report was read but not independently reviewed/rerun. On resume, read AntiGravity's final report and status before editing or assuming ownership. No runtime broker activation or installer rebuild is authorized by this handoff.

2026-11-02 handback accepted: Codex owns skill_broker.py, its tests/T-17 and check.ps1 again. Old transfer notes are historical. Review found malformed op values raised TypeError, invalid Unicode/duplicate JSON fields were not safely rejected, nonfinite deadlines could bypass expiry, adapters could mutate the stored argument snapshot, and generation changes did not invalidate future calls. Fixed with 16 added regressions; existing 15 tests still pass (31 total). Output encoding now bounds the slice before UTF-8 allocation and rejects non-text/invalid text. Broker remains preparation-only, not active transport/routing.

AntiGravity next: ANTIGRAVITY_NEXT.md A8/A9, no backend changes. Owner acceptance guide contains inaccurate PBKDF2/hex-recovery claims and UI verification overclaims; corrections are specifically listed. Browser layout verification remains unproven by builds/static CSS inspection. Combined tests running; installer unchanged.

Final 2026-11-02 checkpoint: tools/check.ps1 -Only tests completed exit 0 after all broker corrections (backend + memory + frontend/build + Electron syntax + JS including settings). No processes/builds left running. Latest log: docs/runs/latest.txt. Broker transport and effectful-skill migration are not implemented; no full-project completion claim. AntiGravity can begin A8/A9 and build now. Next Codex task needs a scoped bounded transport/read-adapter design before activation; preserve existing approval and storage checks.

Colibri selective-adoption request: added COLIBRI_ADOPTION.md and T-18. No vendor code/dependency/model imported. Corrected tools/bench_gpu.py to use Llama3 versus ChatML prompts, label chunks rather than tokens, and report failed/empty runs through exit status. Syntax/prompt construction checked without loading models. No new benchmark result. AntiGravity queue extends to A10 after A8/A9, with explicit ownership only for Model Selection display and a synthetic test. No builds running; no Colibri backend activation or unsupported memory/speed estimates authorized.

Autonomous next step T-19: added broker_protocol.py plus test_broker_protocol.py. One complete length-prefixed frame dispatches through existing authority; 8 KiB request and 16 KiB encoded JSON response limits, malformed/failed exchange revocation, replay refusal and fixed safe child-facing errors. No sockets, subprocess launches, dependencies or production routing changes. 47 focused broker checks pass. Full backend regression running. Next implementation still needs timed/cancellable pipe I/O and a separately scoped read adapter; framing alone is not live isolation.

T-19 final verification: **712 backend tests passed in 34.72s**. No tests/processes left running. Usage snapshot: 69% five-hour, 44% weekly (2026-11-02). Current app routing/installer unchanged by framing. AntiGravity queue remains A8/A9/A10. Next Codex task must scope actual pipe transport and process binding; include partial-read/EOF/timeouts/lock/cancel/process-death tests before any live document adapter. Owner is unavailable; do not treat missing consent/hardware enrollment as passed.
