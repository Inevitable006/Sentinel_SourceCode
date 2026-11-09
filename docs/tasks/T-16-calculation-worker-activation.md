# T-16: Activate contained calculation tools

Owner authorized independent backend progress, 2026-11-01. Branch phase1/security. Scope: skill_router.py, pure_skill_worker.py, focused security tests, capability/coordination records. No frontend, skill-source, pin, dependency or public API changes. Existing SecureRunner policy, owner switches, rate limits, token consumption and audit remain authoritative and unchanged.

Route only the four existing business/technical tool aliases to their pinned worker before parent module loading or capability injection. Preserve output/failure/counter behavior. Fail closed; no in-process fallback. Guard worker entry/result with encrypted database availability and a vault-lock generation; register active request IDs for lock cancellation. Do not transmit IDs/keys/tokens to the child. Test approval refusal, single-use tokens, job identity propagation, lock result suppression and real calculator answers. Full backend regression required before checkpoint.

This remains partial isolation: effectful skills and the permission broker are unfinished. Existing installer remains until both frontend review and release checks pass.

## Report
Completed this bounded activation task, 2026-11-01. SkillRouter sends only the four allowlisted aliases to run_pure before parent module loading or capability injection. Existing output/failure handling and call counters remain. Worker checks database availability, tracks request IDs only in parent memory, cancels on vault lock and suppresses results from an earlier lock generation. No fallback to in-process calculation.

Changed: backend/app/core/skill_router.py, backend/app/core/pure_skill_worker.py; added backend/tests/security/test_calculation_routing.py; updated capability/coordination records. No frontend, public API, skill source, hash pin or dependency changes.

Focused checks: 52 passed in 3.72s. Full backend regression: **665 passed in 33.38s**, exit 0, tools/check.ps1 -Only pytest. Includes real worker calculations, resource limits and cancellation plus approval/token/job-routing and lock-result checks. No running checks/processes left. Installer has not been rebuilt; activation is verified in the development backend only.

Next backend task: design/test the approved-effect broker before moving effectful skills. Preserve checks in SecureRunner and enforce per-request capability messages, revocation on lock/cancel, bounded responses, no exported vault/session credentials, and no duplicate file/network policy implementation. Create the next scoped task before edits. Advanced voice, all-skills isolation and owner hardware/provider/clean-machine acceptance remain incomplete.
