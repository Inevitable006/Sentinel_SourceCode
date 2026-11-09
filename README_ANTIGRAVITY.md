# Sentinel: AntiGravity and Codex development guide

Coordination baseline: 2026-10-31. Repository: this directory. Branch: `phase1/security`.

**Current coordination (2026-11-02):** the six-hour handoff is complete; Codex has resumed and accepted backend/check-script ownership back. AntiGravity's next authorized queue is `docs/coordination/ANTIGRAVITY_NEXT.md` (A8 guide accuracy and A9 actual rendered settings verification). The old six-hour backend/build transfer is no longer active. No need for repeated prompts within the new queue.

After A8/A9, continue **A10 model-status clarity** in `docs/coordination/COLIBRI_ADOPTION.md`. It authorizes only a bounded Model Selection display change using existing data, not Colibri engine installation. Its exact SettingsPanel ownership exception supersedes the old import/mount-only rule for that section.

The owner has authorized parallel development by AntiGravity and Codex. Build a dependable, private personal assistant with small, complete changes. This file is the standing task brief: no fresh prompt is needed for each READY task below. It does not authorize broader features, security changes or edits outside your assigned files.

## 1. Read before editing

1. Read `AGENTS.md`, `docs/ROADMAP.md`, `docs/CAPABILITIES.md` and this guide.
2. Read both files in `docs/coordination/` for current ownership, progress and blockers.
3. Inspect the actual source and `git status --short`. This checkout already has substantial staged AND unstaged work. Preserve both. Older tracker rows are historical; never undo working code to match an old status entry.
4. Choose the first unfinished READY task assigned to you. Record IN_PROGRESS and exact file paths in your own status file before editing. Only one task per agent should be actively edited at a time.
5. Use the completion checks below. Report evidence, then move to another READY task with different files. Never promote a WAITING task yourself.

If instructions conflict, respect the owner's latest instruction and repository safety rules. Record ambiguity in your status file; continue independent assigned work instead of guessing at another agent's implementation.

## 2. Current baseline: keep it usable

Verified on 2026-10-31: 627 backend tests, 13 memory checks, 18 JavaScript checks, frontend build and Electron syntax checks. Real offline semantic search passes with SQLCipher storage, deletion and lock refusal, including the packaged runtime. Installer rebuilt successfully. These are historical verification results, not a promise that future edits pass.

Already implemented: local chat, explicit tool approvals, PIN/vault, encrypted memory/backups, dictation, Windows speech, document keyword/meaning search, tasks/plans/drafts, Google read-only connector, system watch and professional calculators. Reuse these; do not create replacement frameworks.

Still incomplete: advanced voice/identity, complete skill process isolation, call/CPU-temperature detection and live account/hardware/clean-machine validation. Google consent needs the owner. Native dependencies and sensors may be unavailable: show that honestly. The previous SQLCipher Windows policy block no longer reproduces; do not disable Windows protection or replace encryption.

## 3. Ownership and collision rules

| Owner | May edit |
| --- | --- |
| AntiGravity | Exact paths authorized by A1–A3 and A5–A7 below, plus `docs/coordination/ANTIGRAVITY_STATUS.md`; A4 requires a published contract |
| Codex | Backend, backend tests, Electron main/preload, dependencies, package/build tools, shared API clients, root routing/navigation, this guide and API contract, release records and `docs/coordination/CODEX_STATUS.md` |
| Owner | Credentials, Google consent, real microphone/identity enrollment, deployment decisions and personal-data acceptance |

Codex must not edit AntiGravity-owned paths during this assignment. If a backend change requires a frontend change there, record the request in CODEX_STATUS instead. AntiGravity must not fix backend/authentication, modify hashes or dependencies, or change `frontend/src/lib/backend.ts`, `App.tsx`, Sidebar, Unlock or Chat files. Read those files as needed.

No simultaneous ownership of a file, even for different lines. Record a requested transfer; the current owner must explicitly release it in their status file before the other begins. READY_FOR_REVIEW does not release ownership. Codex reviews read-only first and requests corrections in CODEX_STATUS; AntiGravity applies corrections in its own files.

Do not run git reset/clean/checkout/restore, bulk reformatters, dependency upgrades, commits, pushes or branch/worktree changes. Do not stage/unstage someone else's changes. Do not delete unfamiliar files. Worktrees may be introduced later with an explicit shared baseline; a fresh worktree today would omit uncommitted work.

Only Codex runs combined full-suite checks and installer builds, avoiding collisions in shared build outputs and `docs/runs/latest.txt`. AntiGravity may run its focused frontend build; announce it in ANTIGRAVITY_STATUS and check CODEX_STATUS first. Do not run two frontend builds together. Neither agent launches tests against real APPDATA or closes the owner's running app.

## 4. AntiGravity queue

### A1 — Setup/readiness panel — READY

**Outcome:** Settings explains what is usable now and what needs setup, without claiming the whole project is complete.

Allowed files:
- New `frontend/src/components/Settings/ReadinessPanel.tsx`
- New `frontend/src/components/Settings/ReadinessPanel.css` if existing styles are insufficient
- `frontend/src/components/Settings/SettingsPanel.tsx`: only import and mount ReadinessPanel near the top; do not refactor existing settings logic

Implement against `docs/coordination/READINESS_API.md` version 1. Codex implements the endpoint separately. Use existing `apiGet`; never hardcode a session token or backend URL. No new libraries, browser storage of returned data, polling loop, network services or setup side effects. One request on mount and an explicit Refresh are sufficient. Ignore late responses after unmount. Do not duplicate Google, voice or backup controls; explain where the existing controls are.

Handle loading, empty/invalid response, offline backend, 404 (endpoint not integrated yet), 401/423 (session/lock), retry and each documented state. A failed refresh must not leave old green readiness badges presented as current. Render provider text as text; no raw HTML. Use accessible headings, labelled buttons, keyboard focus and non-colour-only status labels. Narrow layouts must not overflow. Avoid a global “everything ready” badge.

While the endpoint is absent, implement against the contract and inspect synthetic states in a development-only harness if needed. Do not ship fake-success data or add a mock backend. Missing endpoint is a real unavailable state, not permission to edit backend code.

Completion: frontend builds; record which UI states were actually exercised and which remain unverified. Record API integration pending if C1 is not ready. Leave the existing app working.

### A2 — Existing settings interaction reliability — READY after A1 is reported

Allowed files: `frontend/src/components/Settings/GoogleSettings.tsx`, `VoiceSettings.tsx`, `BackupSettings.tsx` only. Keep styles local or reuse existing classes; do not edit shared SettingsPanel.css.

Inspect first. Change only observed problems: duplicate submission, missing pending/disabled state, confusing errors, stale status after failure, missing labels or keyboard access. Reuse existing endpoints and PIN controls. Preserve confirmations, stop/lock handling, read-only Google scope and backup/restore wording. No new send/event-write, microphone, credential persistence or automatic network actions.

Completion: record each concrete issue and its fix, frontend build, focused interaction checks using synthetic data. Do not require a real Google login, recording or backup of owner data. If no issue is found, report NO_CHANGE_NEEDED; do not manufacture a refactor.

### A3 — First-run and recovery instructions — READY after A2 is reported

Allowed file: new `docs/USER_QUICKSTART.md` only.

Write a short step-by-step owner guide based on the real UI: setup/PIN and recovery key, local model availability, a first typed chat, approving a harmless action, saving/searching a document, dictation review-before-send, optional Google read-only setup, backup/restore, stop/lock/offline controls and where to find errors. Link existing GOOGLE, VOICE and DOCUMENT_SEARCH docs rather than copying technical setup details. Explain unsupported/unverified features honestly. Never ask the owner to paste credentials into chat or disable Windows security. Include an acceptance checklist the owner can perform without destructive actions.

Completion: check every menu/control name against source; distinguish automated checks from owner-only checks. No speculative instructions or claimed clean-machine verification.

### A4 — Advanced voice UI — WAITING

Before A4, finish **A2 final verification — READY (2026-11-01)**: preserve the exact PIN string in BackupSettings retry (do not trim credentials); correct USER_QUICKSTART's PIN expiry to five minutes since successful verification rather than inactivity. Add `frontend/tests/settings-retry.test.mjs` as the only additional authorized path, using existing Node/TypeScript tooling to exercise actual BackupSettings handlers with synthetic API responses. Verify create/save dispatch, cancellation, exact whitespace-containing PIN preservation and stale load rejection. Do not merely reimplement the handlers in a simulation. No dependencies, owner data or backend edits. Record the reproducible command in ANTIGRAVITY_STATUS. Coordinate builds through CODEX_STATUS.

Do not implement yet. Codex must publish the actual supported engine/phrase/enrollment API and privacy lifecycle before any UI promises wake-word or identity functionality. Keep the existing dictation controls usable. This row is a dependency reminder, not an authorization to build placeholders.

### Standing parallel queue — owner authorized 2026-11-01

Execute in order: **A2 final corrections → A5 → A6 → A7**. After each bounded task, record results and proceed to the next without waiting for a new prompt or Codex review. Check CODEX_STATUS once at task boundaries for new findings/build reservations. Correct actionable review findings in your owned files before starting unrelated work. A4 remains dependent on the actual voice contract. This queue supersedes the old instruction to stop immediately after A3.

### A5 — Reproducible settings behavior checks — READY after A2 corrections

Owned paths: existing A2 components and `frontend/tests/settings-retry.test.mjs`, `frontend/tests/settings-status.test.mjs`; optionally one shared test helper `frontend/tests/settings-harness.mjs` only if reused by both. Do not modify package manifests or Codex's tools/tests files.

Use existing Node and TypeScript tooling, no new packages. Exercise actual component handlers with synthetic local API adapters, not a separately reimplemented state machine. Start with the backup regression test already authorized above; reuse it rather than duplicate it. Cover:
- Correct create/download retries after PIN-required response; preserve exact PIN and selected backup name; Cancel clears pending work and PIN; repeated submission while pending causes at most one operation.
- Initial load, failed load, retry and out-of-order/unmounted responses for backup, voice and Google status. Failed status must not claim current success. Preserve existing confirmation and read-only Google flows.
- Voice save/preview pending and error behavior; credentials import failure clears previous pending credentials. Use synthetic credentials only.

Fix only defects demonstrated by these checks within A2 paths. Report unavailable DOM/browser coverage explicitly. Commands should be executable from the repo root, e.g. `node --test frontend/tests/settings-*.test.mjs`. Do not create a general testing framework or exhaustive implementation-mirroring tests. Report NO_CHANGE_NEEDED where already covered.

### A6 — Settings usability verification — READY after A5 report

Owned edits: A1 ReadinessPanel.tsx/css and the three A2 components only; SettingsPanel.tsx remains import/mount-only. Verify keyboard access, focus visibility, accessible labels, pending/error announcements, and readable narrow layout. Use an isolated synthetic UI fixture if supported; do not operate the owner's accounts, recordings or backups. Distinguish actual browser checks from static inspection. No design overhaul, new dependencies, shared CSS changes or backend edits. Make only observed small fixes and rerun affected checks; avoid another build until this bounded batch ends.

### A7 — Owner acceptance guide and handoff — READY after A6 report

Owned edits: `docs/USER_QUICKSTART.md`, new `docs/OWNER_ACCEPTANCE.md`, and your status file. Keep quickstart concise and remove duplicate technical details in favor of existing docs. Verify every step/control against source; say which checks create synthetic test data. Acceptance guide: typed local chat, approval/deny, document preparation/search, dictation review, voice preview, lock/offline, optional Google consent and encrypted backup. Separate safe current-machine checks from restore/clean-machine checks requiring an isolated environment. No destructive restore on the owner's active profile. Never claim guarantees beyond code/tests, permanent unsupported features, live consent, hardware quality or a clean-machine pass.

Final handoff lists exact files, reproducible commands/results, defects fixed, unverified checks and retained ownership. Report QUEUE_EXHAUSTED after A7 if A4 has not been enabled. No invented features or continuous polling.

## 5. Codex queue

1. **C1 READY:** implement the version-1 readiness endpoint in `READINESS_API.md`, using existing services and authenticated/unlocked Workspace routing. Read-only, bounded, no downloads/model loads/remote calls. Test status/error mapping, lock/auth boundaries and absence of side effects. Notify AntiGravity through CODEX_STATUS when the endpoint is ready.
2. **C2 WAITING on A1/C1:** integrate and validate the complete first-run/readiness experience, reviewing A2/A3 reports. Codex requests frontend corrections instead of editing reserved files. Run the combined suite and packaged-runtime smoke; keep a working installer checkpoint.
3. **C3 PARALLEL backend lane:** design and incrementally implement skill process isolation with resource limits and a broker for approved effects. The owner authorized independent backend progress while A2/A5–A7 proceed. Backend activation needs its own scoped task, unchanged public APIs, policy/approval/lock/cancellation checks and passing regression tests; it no longer depends on frontend documentation acceptance. T-15 preparation remains inactive until that activation task is complete. Final release still waits for C2. Never export vault keys/session credentials to workers or bypass tool approvals. Start with pure tools, then expand with crash/cancel/permission tests. Partial isolation must be labelled partial.
4. **C4 AFTER C3 design is stable:** select supported local voice components, pinned models/dependencies and licenses; implement opt-in microphone lifecycle, cancellation/resource handling and PIN fallback. Voice recognition alone must not authorize sensitive actions. Publish a concrete contract before enabling A4. Real owner enrollment is a separate acceptance step.
5. **C5 RELEASE:** resolve remaining system-awareness capability gaps where the hardware exposes trustworthy signals; unavailable sensors stay unknown. Complete backup/restore, installation, offline and recovery acceptance checks. Do not equate unsupported hardware or missing credentials with successful validation.

Dependency rule: frontend review must not block independent backend work with unchanged interfaces. Release integration joins both lanes after their checks pass. Advanced voice UI still waits for an implemented contract. Do not rewrite working chat, memory or UI architecture merely to match a preferred framework.

## 6. Definition of complete

For each task: a working user-visible outcome; scoped diff; no duplicate capability/dependency; existing approvals and privacy intact; meaningful checks pass; errors and cancellation handled; owner-only checks named; report updated. A task can be READY_FOR_REVIEW with a clearly stated external verification dependency, but cannot be called fully verified.

For a release checkpoint, Codex checks backend regressions, memory checks, frontend/typecheck, Electron/JS checks, actual packaged resources and relevant real offline model smoke. Then build the installer. No private database/log/key/.env in the package. Clean-machine install and hardware/provider behavior are separate checks. Fix a failed essential check before stacking further features onto it; do not suppress or weaken tests.

Use these status values: NOT_STARTED, IN_PROGRESS, READY_FOR_REVIEW, NEEDS_FIX, ACCEPTED, BLOCKED, NO_CHANGE_NEEDED, QUEUE_EXHAUSTED. A compile-only pass is not interaction validation. A mocked provider pass is not live account verification.

## 7. Communication without repeated prompts

Each agent edits only its own status file. At the start and end of a task, record task ID, exact paths, result, checks, blockers and requests for the other agent. Keep reports short and current; retain completed-task summaries below the current entry. Never place credentials or user content in these files.

Codex maintains this guide and the API contract. AntiGravity reads those files when it starts a task; Codex reads AntiGravity's report before integration. Shared files do not mean either agent can see the other's chat or is automatically running. The owner can simply ask either agent to continue from this guide.

## 8. Usage budget and safe checkpoints

Owner requirement: reserve enough allowance to leave a working checkpoint before usage reaches 95%. Treat this as an engineering guardrail, not a guarantee of an exact token count or uninterrupted access. Other chats can consume shared limits, reported usage can lag, and interruptions can occur without warning.

- Codex checks its available account usage tool at task start, before a substantial new task and after a completed milestone. Use the most-used applicable limit window. These are account usage percentages, not this project's token counter or an API-dollar balance. Do not purchase credits, consume reset credits or change plans automatically.
- AntiGravity checks its provider's actual usage indicator if accessible. If unavailable, report UNKNOWN rather than inventing a balance. Use one small subtask per checkpoint and ask the owner to relay a low-allowance warning. Codex cannot read AntiGravity's balances.
- Below 80% used: perform bounded tasks, with completion checks and handoff updates after each.
- At 80–89%: start no large refactor, migration, dependency/model installation or cross-component feature. Finish only a small task that leaves room for verification and recovery.
- At 90–94%: stabilization only. Do not start another feature. Run relevant checks, correct regressions within the current scope, update the handoff and leave the next step explicit.
- At 95% or above: do not start implementation. Use remaining allowance for the shortest truthful status/handoff and essential containment of an already-started change. Do not claim that a broken or untested checkpoint is safe.

Every task begins with a runnable baseline or an explicit existing failure. Build additions behind existing stable entry points; do not expose unfinished controls or replace a working path before its replacement is tested. Write minimal progress notes before long operations, not only at the end. If interrupted, the next model must inspect current files and running checks before doing more work.

If a new change breaks the baseline, fix it or manually undo ONLY your own clearly identified edits when safe. Never use blanket git restore/reset, remove someone else's staged work, substitute plaintext for encrypted storage, suppress tests or present mock success. If safe recovery needs another owner's files or cannot finish, record the exact failing path/check and preserve the last verified installer. Do not rebuild or label a new release while essential checks fail.

Checkpoint entry in your own status file:

```text
Task/subtask and state:
Usage source, checked time, used percentages (or UNKNOWN):
Files changed by this agent:
Last verified runnable checkpoint and commands/results:
Unverified changes or current failures:
Running processes/checks that the next agent must inspect:
Recovery action taken, if any:
Exact next step and dependencies:
File ownership retained or explicitly released:
```

Switching Gemini/Claude/another model inside AntiGravity does not create a second owner. Stop the old worker before the new one writes the same lane; the new model reads this guide and ANTIGRAVITY_STATUS and resumes the exact task. It must not restart, rewrite or expand scope merely because the model changed. Review-only sessions may inspect files but must not edit or run shared builds while the implementation worker is active.

To conserve allowance, read relevant files/diffs, batch independent inspections, use focused behavioral checks while developing, and let Codex run the combined release checks once integration is ready. Avoid repeating full repository scans, passing test suites, installer builds or long status summaries without a new reason. Model choice does not relax privacy, approval or verification requirements.
