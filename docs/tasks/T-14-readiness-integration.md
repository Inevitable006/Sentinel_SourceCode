# T-14 / C2: Readiness integration checks

Branch: phase1/security. Codex owns tools/tests/readiness.test.mjs, tools/check.ps1 and coordination reports. AntiGravity retains its frontend files.

Scope: exercise the actual readiness component with controlled hook and API adapters using existing TypeScript and Node tooling. Verify malformed responses, failed refresh, out-of-order completion and cleanup without owner data, network or new dependencies. This is a component logic check, not a browser rendering or Electron IPC test. Preserve existing tests. Run focused checks; postpone installer rebuilding until A2/A3 settle.

## Report
Completed the component-logic portion, 2026-11-01. Added tools/tests/readiness.test.mjs and registered it in tools/check.ps1. The check transpiles the actual TSX using the existing TypeScript installation and supplies controlled React hook/API adapters; it does not copy the validator or request logic.

Verification: node --test tools/tests/readiness.test.mjs tools/tests/voice.test.mjs tools/tests/safe-mode.test.mjs tools/tests/os-lock.test.mjs tools/tests/packaging.test.mjs — 24 passed, 0 failed. Six readiness tests cover malformed payloads, failed refresh, StrictMode out-of-order replies, unmount, pending-request preservation and invalid refresh. No frontend edits, added dependencies, network or owner data used.

Remaining C2: A2/A3 review, browser/Electron rendering and IPC verification, then final combined checks and installer refresh. The hook adapter is deliberately not evidence of DOM accessibility/layout or live Electron behavior. Prior backend checkpoint remains 640 passed; unchanged backend was not rerun.
