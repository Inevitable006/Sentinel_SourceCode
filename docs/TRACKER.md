# Sentinel tracker

Live status of the work. Claude updates it as each step finishes.
✅ done · 🔄 in progress · ⏳ next · ⛔ needs you · 💤 later

- Plan and decisions: `docs/ROADMAP.md`
- What changed, in plain words: `CHANGELOG.md`

_Last updated: 2026-09-27_

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
| 1b | GPU sidecar (D1): 7B models at ~44 tok/s | ⏳ next |
| 2 | Voice & identity (wake word, speech-to-text, voice ID, Windows Hello option) | 💤 |
| 3 | Smarter brain: planner, tool calling, prompt-injection defense, file search | 💤 |
| 4 | System control & automation (undo, scheduler, emergency stop) | 💤 |
| 5 | Skills, each in its own process | 💤 |
| 6 | Integrations & privacy dashboard | 💤 |
| 7 | Hardening & installer | 💤 |

## Done
| Date | What |
|---|---|
| 2026-09-27 | Phase 1 security foundation: egress guard, PIN unlock, encrypted DB, secrets vault, redaction, retention; independent review fixed |
| 2026-09-27 | Phase 1 plan approved (decisions D1–D5) |
| 2026-09-27 | Phase 0 stabilize: 158 tests, chat smoke test and Electron start green on Windows |
