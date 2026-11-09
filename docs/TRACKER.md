# Sentinel tracker

Parallel development entry point (2026-10-31): `README_ANTIGRAVITY.md`. AntiGravity owns the bounded A1–A3 frontend/documentation queue; Codex owns backend/security and release integration. Read `docs/coordination/ANTIGRAVITY_STATUS.md`, `CODEX_STATUS.md` and the versioned readiness contract before editing. Neither agent's chat is automatically visible to the other.

Live status of the work. Claude updates it as each step finishes.
✅ done · 🔄 in progress · ⏳ next · ⛔ needs you · 💤 later

- Plan and decisions: `docs/ROADMAP.md`
- What changed, in plain words: `CHANGELOG.md`

_Last updated: 2026-10-17. Latest checkpoint: `docs/tasks/T-09-roadmap-completion.md`, `T-10-google-workspace.md`, and `T-11-document-retrieval.md` (619 backend tests + 28 code analysis tests pass). Historical rows below are not the current feature inventory; see CAPABILITIES and the completion ledger._

## Current development checkpoint

Phase 10 packs now include research/writing, business/marketing calculators, technical conversions/estimates, encrypted document retrieval (T-11), and expanded code analysis tools (outline, stats, imports, references). Scheduled plans, battery/GPU-heat controls and Google read-only connection code are implemented. Real GPU chat passed. Full roadmap is **not complete**: advanced identity, learned semantic retrieval, full skill process isolation, and live account/clean-machine validation remain open (T-09/T-10).

Resumed from `9a0668b` on `phase1/security` (Phase 10 coding pack). Coding test runs now reject empty and entirely skipped suites instead of reporting success. Verification results are recorded in T-04. The older phase table below is historical; use `docs/CAPABILITIES.md` for implemented features, including dictation, vision, workspace actions and backups. Clean-machine installation and owner hardware checks remain unverified.

## Needs you (owner)
| # | What | Why | Status |
|---|---|---|---|
| O1 | Make the GitHub repo `Inevitable006/Sentinel_SourceCode` private: repo **Settings → General → Danger Zone → Change visibility → Private** | The project is personal, but anyone can read the code today. GitHub asks for your password, so only you can do it. | ⛔ open |
| O2 | Open Sentinel and choose your PIN (8+ characters, or 10+ digits). Save the recovery key it shows (paper or password manager). Type the PIN only into Sentinel, never into a chat. | Encrypts your data and moves the old database into the encrypted one | ⛔ ready now |

## Phase 1: Security foundation ✅ (merged to `main`)
| Step | Task | Status | Notes |
|---|---|---|---|
| 1.0 | Setup: watcher, `AGENTS.md`, tracker, change notes | ✅ | commit 53d2af0 |
| 1.0 | Governor reads the GPU through NVML, off the event loop | ✅ | 174 tests pass, real RTX 3050 read |
| 1.0 | Dependency sync on Windows (`deps` check) | ✅ | also `pytest` + `probe` checks |
| 1.1 | Egress guard: allowlist, network-tool rule, offline switch, log of every call | ✅ | `app/core/egress.py` |
| 1.1 | Tests run fully offline (socket guard) | ✅ | caught 5 tests doing real DNS lookups |
| 1.1 | Electron blocks non-local requests; "online" indicator in the UI | ✅ | telemetry panel now live (was fake numbers) |
| 1.2 | WebSocket session token out of the URL | ✅ | server log no longer contains it |
| 1.3 | Owner unlock: data key wrapped by PIN (Argon2id) + Windows login (DPAPI), recovery key | ✅ | `app/core/vault.py`, `dpapi.py` |
| 1.3 | Unlock screen, auto-lock when idle, PIN re-check before Tier-3+ actions | ✅ | D6: Tier 3+, 5-minute window |
| 1.4 | Encrypted memory DB + migration (backup → encrypt → verify) | ✅ | SQLCipher; old file kept until you delete it |
| 1.4 | Drop test-created rows during the migration (D2) | ✅ | exact-match rules only |
| 1.5 | Secrets vault inside the encrypted store; log redaction | ✅ | `secrets_store.py`, `redaction.py` |
| 1.6 | Real deletion + retention defaults | ✅ | chats 180 d, research 90 d; `retention.py` |
| 1.6 | Real "Forget all memories" in Settings | ✅ | plus "Delete all chat history" |
| 1.6 | Move research history (`research_history.json`, plaintext) into the encrypted store | ✅ | done with the review fixes |
| 1.x | Full Windows check + independent security review | ✅ | 287 tests, quick check green, 11 review findings fixed |

## Later phases
| Phase | Scope | Status |
|---|---|---|
| 1b | GPU sidecar (D1): local implementation verified | ✅ 324 tests, 13 memory checks, frontend build and real 7B GPU chat passed 2026-10-03; committed 2026-10-10 (0173f2a) |
| 2 | Voice & identity | 🔄 Local dictation implemented; real runtime blocked by Windows Application Control (PyAV). See `docs/VOICE.md`. Wake word, voice ID and Hello remain pending. |
| 3 | Smarter brain: planner, tool calling, prompt-injection defense, file search | 💤 |
| 4 | System control & automation (undo, scheduler, emergency stop) | 💤 |
| 5 | Skills, each in its own process | 💤 |
| 6 | Integrations & privacy dashboard | 💤 |
| 7 | Hardening & installer | 💤 |
| 8 | System Watch (T-06): local change alerts, defensive only | ✅ first version 2026-10-10 |
| 9 | Portfolio Advisor (T-07): advice only, no trading | ✅ first version 2026-10-10 |

## Done
| Date | What |
|---|---|
| 2026-10-10 | Portfolio Advisor (advice only, no trading) — 5892edc |
| 2026-10-10 | Voice choice (male/female) + speech speed — 6d29f62 |
| 2026-10-10 | Audit findings F01–F23 fixed, System Watch (T-06), project tidy — 0173f2a |
| 2026-09-27 | Phase 1 security foundation: egress guard, PIN unlock, encrypted DB, secrets vault, redaction, retention; independent review fixed |
| 2026-09-27 | Phase 1 plan approved (decisions D1–D5) |
| 2026-09-27 | Phase 0 stabilize: 158 tests, chat smoke test and Electron start green on Windows |

2026-10-25 update (T-12): local semantic retrieval is implemented using a pinned English BGE GGUF and the existing CPU engine. Native offline smoke and frontend build pass. Encrypted integration testing is blocked by Windows Application Control refusing the existing SQLCipher library; the owner is arranging approval. Previous regression counts do not validate these new changes. See `docs/DOCUMENT_SEARCH.md` and `docs/tasks/T-12-personal-assistant-completion.md`. The installer has not yet been rebuilt for this increment.

2026-10-31: SQLCipher blocker no longer reproduces. Semantic retrieval passes 17 selected tests, full suite 627, and real offline encrypted smoke. Installer rebuild and actual bundled-runtime encrypted semantic smoke pass; T-12 records verification. Remaining roadmap work is unchanged.
