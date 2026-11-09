# T-09: Complete the remaining roadmap

Owner instruction 2026-10-17: "do fully" / "all". Continue on `phase1/security`; preserve existing changes; no pushes.

## Scope
Implement the remaining professional packs, finish and verify local workflows and packaging, reconcile the roadmap against actual code. Reuse existing components. No new dependencies, cloud services or machine-security changes. Existing approval, PIN, egress and data-isolation boundaries remain in force. Changes may include skills/registration/pins/tests, frontend, local APIs, packaging tools and project documentation. Authentication or provider design changes need a specific implementation scope before editing them.

## Completion ledger
- Research/writing first version: complete (T-08).
- Marketing/business: implemented/tested; deterministic unit economics and campaign metrics.
- Technical: implemented/tested; dimension-checked conversions and transfer estimates.
- Local runtime/installer: bundled runtime and actual packaged backend both import and register 14 skills; installer rebuilt successfully with full-screen pause support (1,480,785,231 bytes). Clean-machine installation still unverified.
- Local chat/GPU smoke: PASS with isolated data; Qwen 7B on GPU, load 4.6 s, first chunk 1.2 s, complete response; no sidecar remained after backend termination.
- Phase 2 advanced voice/identity: wake word, voice enrollment, Windows Hello and Piper are not implemented; dependencies/models/hardware/enrollment required.
- Phase 3 retrieval: encrypted semantic document retrieval is not implemented; design/model choice remains open.
- Phase 4: scheduled plans implemented and tested (time/resources gate, explicit per-step approval, cancellation, live status refresh). Battery and GPU-heat pause/recovery implemented. Windows full-screen/presentation detection implemented through SHQueryUserNotificationState; CPU thermal and call detection remain unimplemented.
- Phase 5 per-process execution of every skill: not implemented; only Python execution has containment.
- Phase 6: owner selected Gmail/Google Calendar. Read-only OAuth connector and Settings UI implemented/tested (T-10); live account consent still required. Local drafts/privacy dashboard exist; sending and remote event changes remain unavailable.
- Phase 7: standalone threat model saved through Codex Security, with independent architecture review; local GPU performance smoke verified. Clean-machine install remains unverified.

## Report
Current verification: `582 passed in 30.64s`, memory `13/13`, 17 JavaScript checks, frontend typecheck/build and Electron syntax checks pass. Real GPU chat smoke passes. Packaged Python imports current backend/Google routes and registers 14 skills. No new dependencies. Google is the only new provider traffic, explicitly selected by the owner and mediated through the existing egress guard.

Files: two professional skill modules, skill registration/pins/behavioral tests; Workspace API/UI scheduling and tests; resource governor/status UI and tests; Google service/routes/Settings and tests; roadmap/capabilities/setup/completion documentation. Earlier coding and writing changes preserved. No commits or pushes.

The full roadmap remains incomplete. Advanced voice features require additional pinned model/runtime choices and real enrollment; learned semantic retrieval needs an embedding model and encrypted index lifecycle; full skill process isolation needs a broker design for approved effects and encrypted data without exporting vault keys to workers. These are substantial unfinished implementation items, not features certified by the passing checks. Call detection and clean-machine/hardware/provider validation also remain open. Do not equate passing regression tests with roadmap completion.

Latest increment: Windows full-screen/presentation pause and recovery, ten additional behavior/API-failure tests; all 582 backend tests pass. Installer rebuilt successfully. Threat model: C:/Users/shamb/.codex/state/plugins/codex-security/scans/Sentinel_SourceCode/artifacts-734465ccb2a9c45486979f18f3d6c9a0764b75d344e05eb446be41f8cdb82288/threatmodel.md.
