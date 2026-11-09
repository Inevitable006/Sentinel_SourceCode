# T-13 / C1: Read-only readiness endpoint

Owner authorized parallel development, 2026-10-31. Branch phase1/security. Codex owns backend; AntiGravity owns A1–A3 frontend files. Contract: docs/coordination/READINESS_API.md version 1.

Scope: new readiness service, authenticated/unlocked Workspace GET route and focused backend tests. Read cached runtime facts and existing local metadata only. Never load models, start speech, probe hardware, download, call providers, write settings or expose private paths/errors. Optional failure is unknown; session/lock failures stay request-level. No new dependencies or security-setting changes. Preserve staged work.

Checks: six stable IDs, all contract states, failure isolation, privacy, side-effect guards, stale lock/auth refusal. Backend tests only while AntiGravity may build frontend. Combined UI/release checks belong to C2.

## Report
Completed C1. Added backend/app/core/readiness.py and backend/tests/integration/test_readiness.py; registered GET /api/workspace/readiness in backend/app/workspace_routes.py using existing session and owner dependencies.

Verification: tools/check.ps1 -Only pytest — 640 passed in 29.13s, exit 0 (2026-10-31). Includes 13 readiness cases covering contract, optional failures, privacy, cached checks, authentication/lock and forbidden setup side effects. No new dependencies.

C2 frontend integration review is pending AntiGravity corrections recorded in CODEX_STATUS.md. Existing installer predates C1; live Google, microphone and clean-machine acceptance remain unverified.
