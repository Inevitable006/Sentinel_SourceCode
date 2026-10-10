# T-02: Resume verification and make failures visible

- **Goal:** Verify the existing GPU milestone and fix the check runner's false-success exit status.
- **Branch:** `phase1/security` (preserve the existing unfinished work).
- **Files you may change:** `tools/check.ps1`, `tools/smoke_chat.py`, this card, verification reports, `docs/TRACKER.md`, `docs/ROADMAP.md`.
- **Do not change:** Existing GPU/security implementation, dependencies, owner data.
- **Steps:** Run the existing checks; propagate failed commands to the runner exit status; record exact results and outstanding roadmap work.
- **Acceptance:** Backend tests and frontend build checked; runner returns nonzero for failed checks and zero for passing checks.
- **Report (2026-10-03):** Completed verification checkpoint. Changed `tools/check.ps1` to propagate command failures, check both Electron source files separately, reject invalid check modes, and return a nonzero result for PowerShell errors. Changed `tools/smoke_chat.py` to reject unauthenticated access, unsuccessful owner setup, cancelled replies and partial replies followed by errors. Preserved existing GPU implementation and all other unfinished changes.
  - Initial sandbox run: Python blocked (exit 101); frontend build passed; old runner incorrectly returned zero.
  - Repaired failure path: same sandbox restriction returned exit 1.
  - Repaired success path: `324 passed in 18.28s`; memory acceptance `13/13 passed`; frontend typecheck/build and both Electron syntax checks passed; runner exit 0. Evidence: `docs/runs/check_20261003_161854.txt`.
  - Real chat smoke: Qwen 2.5 7B on GPU, load 4.4s, first text 0.3s, roughly 41.6 streamed chunks/s (not a standardized token benchmark), completed reply; no sidecar left after backend termination; exit 0. Evidence: `docs/runs/check_20261003_164056.txt`.
  - `git diff --check` passed. No commits or pushes.
  - Remaining: desktop visual/installer verification and roadmap Phases 2–7. Owner PIN/migration status was not inspected; smoke uses temporary data. GitHub repository remains public as checked through the GitHub connector. This checkpoint does not certify the entire application complete or constitute an independent security audit.
