# T-15 / C3 preparation: bounded calculation worker

Owner renewed full-roadmap scope on 2026-11-01. Branch phase1/security. C2 release integration is waiting on AntiGravity A2/A3. Prepare and verify a worker independently; do not activate routing before that checkpoint.

Allowed edits: new backend/app/core/pure_skill_worker.py, backend/tests/security/test_pure_skill_worker.py and coordination/task documentation. Reuse existing python_sandbox and SafeProcess unchanged. No new dependencies, skill source/pin changes, auth changes or frontend edits.

Design: allow only business_analysis unit_economics/campaign_metrics and technical_analysis convert_units/estimate_transfer. Read and hash-check exact pinned source on every call, send only that source plus bounded JSON scalar arguments to an isolated child through stdin. No vault/session/approval credentials. A minimal failed-result import facade exposes only the existing failure marker semantics; other backend imports are refused. Reuse Windows Job memory/process limits, timeout, output cap, request cancellation and minimal environment. Fresh temporary workspace per call; cleanup after completion. Errors fail closed with no in-process fallback. This is containment for trusted pinned built-ins, not a hostile-code OS sandbox.

Future broker: effects remain in parent after policy, owner switch, rate-limit and approval checks. Workers must never receive vault keys or reusable service callbacks. File/network/database operations need explicit per-operation messages scoped to the already-approved request; responses are bounded plain data, cancellation revokes the request. Do not move effectful tools until broker tests cover stale approvals, lock/cancel, path/egress checks, crash and output bounds.

Acceptance: real worker calculations and failure preservation; reject unknown tools, pin mismatch and non-scalar/oversized/nonfinite arguments; child failure returns failure; cancellation context stays delegated to SafeProcess. Routing activation, full broker and all-skills isolation remain separate unfinished work.

## Report
Worker preparation implemented in pure_skill_worker.py with 13 tests in test_pure_skill_worker.py. Preparation only: not active in runtime routing. Four real Windows child-process calculation cases cover every allowed function; tests also preserve failure semantics and refuse invalid inputs, missing pins and bad process responses. No existing source/pin/security module changed.

Initial full regression: 652 passed; one new campaign test used the wrong output key (`ctr_percent` rather than the existing `click_through_rate_percent`). Corrected that assertion without changing production calculation behavior. Final full backend regression: 653 passed, exit 0 (tools/check.ps1 -Only pytest, 2026-11-01).

Activation remains gated on C2 review corrections. Full isolation, broker, cancellation/lock integration tests and independent security review remain unfinished; this worker must not be described as all-skills isolation or a hostile-code sandbox. The existing Python containment permits temporary-workspace writes and stdlib reads; this phase is limited to trusted hash-pinned calculators.

Follow-up verification, 2026-11-01: 16 focused worker tests passed in 1.14s. Added actual per-request process cancellation and two oversized-output cases (truncated protocol and capture-budget termination), using temporary synthetic modules and test-only pins. Production sources/pins unchanged. Cancelled child returns failure and is removed from active process tracking. This verifies process-level cancellation, not the pending SecureRunner/lock routing integration. No full-suite rerun needed for this test-only increment; previous full run remains 653 passed.

Next containment increment: source reads now stop at 64 KiB plus one sentinel byte instead of allocating the entire file before checking size. Non-string tool identifiers fail closed. Added real child tests refusing socket/backend imports and a 900 MiB allocation under the existing 512 MiB Job limit, plus oversized-source and identifier cases. Focused result: **21 passed in 1.48s**. No changes to production skill pins, frontend files or runtime routing. Full-suite historical result remains 653; it is not a verification of these latest changes.
