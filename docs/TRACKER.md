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
| O2 | Choose your PIN when Sentinel asks for it. Type it only into Sentinel, never into a chat. | Unlock and encryption | 💤 end of Phase 1 |

## Phase 1: Security foundation (branch `phase1/security`)
| Step | Task | Status | Notes |
|---|---|---|---|
| 1.0 | Setup: watcher, `AGENTS.md`, tracker, change notes | 🔄 | |
| 1.0 | Governor reads the GPU through NVML, off the event loop | ⏳ | stops chat stalls of up to 2 s |
| 1.0 | Dependency sync on Windows (`deps` check) | ⏳ | |
| 1.1 | Egress guard: allowlist, approval for new sites, log of every call | ⏳ | |
| 1.1 | Tests run fully offline (socket guard) | ⏳ | |
| 1.1 | Electron blocks non-local requests; "online" indicator in the UI | ⏳ | |
| 1.2 | WebSocket session token out of the URL | ⏳ | |
| 1.3 | Owner unlock: data key wrapped by PIN (Argon2id) + Windows login (DPAPI), recovery key | ⏳ | |
| 1.3 | Unlock screen, auto-lock when idle, PIN re-check before Tier-2+ actions | ⏳ | |
| 1.4 | Encrypted memory DB + migration (backup → encrypt → verify) | ⏳ | |
| 1.4 | Drop test-created rows during the migration (D2) | ⏳ | backup kept |
| 1.5 | Secrets vault inside the encrypted store; log redaction | ⏳ | |
| 1.6 | Real deletion + retention defaults | ⏳ | |
| 1.x | Full Windows check + independent security review | ⏳ | |

## Later phases
| Phase | Scope | Status |
|---|---|---|
| 1b | GPU sidecar (D1): 7B models at ~44 tok/s | 💤 |
| 2 | Voice & identity (wake word, speech-to-text, voice ID, Windows Hello option) | 💤 |
| 3 | Smarter brain: planner, tool calling, prompt-injection defense, file search | 💤 |
| 4 | System control & automation (undo, scheduler, emergency stop) | 💤 |
| 5 | Skills, each in its own process | 💤 |
| 6 | Integrations & privacy dashboard | 💤 |
| 7 | Hardening & installer | 💤 |

## Done
| Date | What |
|---|---|
| 2026-09-27 | Phase 1 plan approved (decisions D1–D5) |
| 2026-09-27 | Phase 0 stabilize: 158 tests, chat smoke test and Electron start green on Windows |
