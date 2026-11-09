# Selective adoption and AntiGravity task A10

Owner request: take useful Colibri parts, 2026-11-02. Adopt model visibility, measured diagnostics and an optional-engine boundary; do not merge repositories. No Colibri code has been imported. Sentinel already has profile selection, fit checks, a resource governor and a GPU benchmark: extend those, do not duplicate them. Reference review: C:/Muthu project/New one/COLIBRI_REVIEW.md.

## Codex lane

Correct existing benchmark prompt templates and misleading token-rate labels (T-18). A later optional Colibri adapter must implement its distinct /v1/completions or /v1/chat/completions protocol, pin binaries/models, enforce per-launch authentication, loopback/process ownership, cancellation/lock cleanup and privacy-safe persistence. Benchmark a supported model first; no default backend switch. Current Qwen2.5 GGUF compatibility with Colibri is not established. Do not download hundreds of GB merely to evaluate UI ideas.

## AntiGravity A10 — model status clarity — READY after A8/A9 report

Allowed edits: only the Model Selection section of frontend/src/components/Settings/SettingsPanel.tsx and, if useful, a small presentational ModelStatus.tsx in the same directory; new frontend/tests/model-status.test.mjs. This is an explicit expansion of the previous import/mount-only SettingsPanel ownership. Do not change its data fetching, model-selection handler, auth, privacy controls, other sections, shared CSS or backend.ts. Update ANTIGRAVITY_STATUS with the chosen exact paths first.

Use only current ModelsInfo fields from frontend/src/lib/backend.ts: active_profile, profiles[].downloaded, loaded profile/name/engine/notes, last_load_error and gpu_engine available/running/vram_mb/reason. No new API, requests, polling, dependencies or model downloads. Distinguish selected profile from actually loaded model, downloaded from loadable, and GPU engine availability from running inference. Auto is a selection policy, not a downloadable model. Show unavailable/unknown information honestly; missing VRAM must never be shown as measured zero. Clear status must not imply every GGUF/model fits or is supported.

Present a short explanation that model weights, context cache and runtime all consume memory, and the current load/fit checks remain authoritative. The existing API does not expose reliable per-model RAM/VRAM fit estimates: do not invent sizes, speed predictions, percentage bars, recommended models or a new download button. Show loaded.notes as reasons for selection/fallback in plain language. Do not display an engine as Colibri: it is not integrated.

Exercise actual rendering/handlers with existing synthetic test tooling: auto selected but a concrete model loaded; selected model differs from loaded; not downloaded; no model loaded; GPU unavailable; runtime missing/invalid vram_mb; prior load error and fallback notes. Preserve existing onChange behavior. If extracting a presentational component, pass existing state as props and avoid duplicate state/fetching. Use labels/focus and narrow layout; no redesign. Run settings/readiness/model-status tests and one frontend build after checking CODEX_STATUS build reservations.

Report exact changes, commands/results and unverified browser checks. Stop after A10; advanced voice A4 and engine integration remain outside your scope. A8 guide corrections and A9 actual rendering verification remain earlier tasks; do not restart already-completed work.

## Reuse/licensing boundary

This task borrows design ideas, not source. If future work copies Colibri code, record upstream revision, source paths, modifications and applicable Apache-2.0/third-party notices; model terms are separate. Do not copy its agent launcher, browser conversation storage, direct network/download helpers or persistent KV behavior into Sentinel without a separately reviewed scope.
