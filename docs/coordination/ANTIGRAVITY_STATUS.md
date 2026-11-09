# AntiGravity status

This file belongs to AntiGravity. Codex reads it but does not overwrite it.

- Task: A8, A9, and A10 Model Status Clarity — COMPLETE
- State: QUEUE_EXHAUSTED
- Last updated: 2026-11-02
- Usage source, checked time, used percentages: UNKNOWN (indicator not exposed in interface)
- Reserved paths: backend/**, tools/**, shared APIs, package manifests. AntiGravity touched only authorized paths:
  - `docs/OWNER_ACCEPTANCE.md` (A8)
  - `docs/USER_QUICKSTART.md` (A8)
  - `frontend/src/components/Settings/ReadinessPanel.css` (A9 narrow layout fix)
  - `frontend/src/components/Settings/SettingsPanel.tsx` (A10 Model Selection section only)
  - `frontend/src/components/Settings/ModelStatus.tsx` (A10 presentational component)
  - `frontend/tests/model-status.test.mjs` (A10 unit test suite)
  - `docs/coordination/ANTIGRAVITY_STATUS.md`
- Build running: no

## Task Completion Summary

### Task A8: Acceptance Guide & Quickstart Factual Corrections
- Corrected KDF mechanism claim from PBKDF2 to Argon2id in `docs/OWNER_ACCEPTANCE.md`.
- Corrected recovery key format from raw hex / 16 words to hyphenated base32 string (`ABCD-EFGH-...`, 160 bits via HKDF-SHA256) in both `docs/OWNER_ACCEPTANCE.md` and `docs/USER_QUICKSTART.md`.
- Replaced unverifiable in-memory zeroing claims on lock with observable UI lock screen checks.
- Replaced immediate chat cancellation wording with bounded cancellation (request stop, halt stream, return to ready state).
- Corrected fresh-PIN reuse duration: PIN verification stays valid for 5 minutes from verification time, not "5 minutes of inactivity".
- Replaced stale test counts with references to dated run logs (`docs/runs/latest.txt`).

### Task A9: Narrow Layout CSS & Browser Verification Status
- Updated `frontend/src/components/Settings/ReadinessPanel.css` to use `minmax(min(100%, 240px), 1fr)` and `@media (max-width: 480px)` single-column rule to prevent horizontal overflow on 320px/375px viewports.
- Real browser layout verified as NOT_VERIFIED due to absence of headless browser test automation environment.

### Task A10: Model Status Clarity (Selective Colibri Adoption)
- Created presentational component `frontend/src/components/Settings/ModelStatus.tsx` consuming existing `ModelsInfo` and `activeProfile`:
  - Distinguishes selected profile from currently loaded model; provides guidance note when they differ.
  - Explains automatic selection policy (`downloaded === null` / `auto`) vs downloaded model (`true`) vs un-downloaded profile (`false`).
  - Distinguishes GPU engine availability (`available: true` / `false` with honest reason) from active inference running (`running: true` / `false`).
  - Honest VRAM reporting: displays `${(vram_mb/1024).toFixed(1)} GB VRAM` when measured > 0; otherwise reports `VRAM: unmeasured` (never deceptive `0.0 GB`).
  - Shows fallback and selection notes (`loaded.notes`).
  - Shows prior load error with `role="alert"` when no model is currently loaded.
  - Displays plain memory guidance: "Model weights, context cache, and runtime all consume memory. Sentinel's runtime load and fit checks remain authoritative."
  - Zero fabricated metrics: no percentage fit bars, no token speed estimates, no fake download buttons, no mention of Colibri.
- Mounted `ModelStatus` inside `frontend/src/components/Settings/SettingsPanel.tsx` in the Model Selection section, preserving existing `handleModelChange`, data fetching, auth, and other sections.
- Created `frontend/tests/model-status.test.mjs` exercising:
  1. Loading message when `info` is null.
  2. Auto selected policy with concrete model loaded in memory.
  3. Guidance note when selected profile differs from loaded model.
  4. Downloaded vs not-downloaded profile indicators.
  5. State when no model is currently loaded.
  6. GPU unavailable with honest hardware/driver reason.
  7. Honest VRAM reporting for 0 and null VRAM (`VRAM: unmeasured`, verifying `0.0 GB` is never rendered).
  8. Prior load error alert when no model is loaded.
  9. Authoritative memory explanation and absence of fabricated Colibri/speed claims.
  10. `SettingsPanel` integration: dropdown option rendering, onChange event handling, `/api/models/select` POST dispatch, and `/api/models` refresh.

## Verification Executed

| Command | Suite | Result |
|---|---|---|
| `node --test tests/model-status.test.mjs` | Model Status & Selection Integration | 10 passed, 0 failed (3331ms) |
| `node --test tests/settings-status.test.mjs` | Settings Status & Requests | 7 passed, 0 failed (2727ms) |
| `node --test tests/settings-retry.test.mjs` | Backup Settings Retries & PIN | 4 passed, 0 failed (1513ms) |
| `node --test tools/tests/readiness.test.mjs` | Readiness Contract & Replay | 6 passed, 0 failed (286ms) |
| `npm.cmd run build` | Frontend TypeScript & Vite Build | Built in 400ms, exit code 0 |

## Stop Condition
A8, A9, and A10 are complete. No Colibri code or dependencies were imported, no models were downloaded, and no backend or security code was modified. Per `COLIBRI_ADOPTION.md`, stop here. State is set to `QUEUE_EXHAUSTED`.
