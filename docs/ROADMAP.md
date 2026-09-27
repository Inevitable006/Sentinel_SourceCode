# SENTINEL: Assessment & Roadmap
_Living plan. Last updated 2026-09-27: **Phase 1 (security foundation) complete** on `phase1/security` → `main`; the owner still has to set the PIN (tracker O2). Next: Phase 1b (GPU sidecar). Status per task: `docs/TRACKER.md`; plain-language change notes: `CHANGELOG.md`._

## 1. Where things stand

**Machine:** i5-12400F (12 threads) · 32 GB RAM · RTX 3050 8 GB · Windows 11 Pro · Python 3.14.3 · Node 24.
**Repo:** `C:\Muthu project\New one\Sentinel_SourceCode` · GitHub `Inevitable006/Sentinel_SourceCode` (found **public** on 2026-09-27, see D3).
**Git:** `phase0/stabilize` is green. `tools\setup_phase1.bat` moves `main` up to it and opens `phase1/security`. Old branch `chore/structure-cleanup` holds the legacy JS engine (incl. the Gemini cloud router) that Phase 0 removed: archive it.

| Layer | Status | Where |
|---|---|---|
| Desktop shell | ✅ Electron + React/Vite, production build loads | `src/main`, `frontend/` |
| Backend | ✅ FastAPI + WebSocket streaming, cancel, one-request guard, confirmations | `backend/app/main.py` |
| Local LLM | 🟡 Works, **CPU only** (python binding has no GPU offload) → D1, Phase 1b | `ai_service.py` |
| System awareness | ✅ Profiler + resource governor; GPU via NVML, off the event loop | `resource_governor.py`, `gpu_monitor.py` |
| Security core | ✅ Policy tiers, single-use confirmation tokens, audit log, sandboxed runner, session token | `policy_engine.py`, `secure_runner.py` |
| Skills | ✅ 7 skills, manifest-based loader / router / verifier | `backend/skills/`, `skill_*.py` |
| Vision | ✅ Secure image ingest + local inference | `vision_*.py` |
| Memory | ✅ SQLCipher-encrypted, closed while locked; retention + real deletion | `db/database.py`, `retention.py` |
| Voice | 🟡 TTS only (pyttsx3) | `voice_service.py` |
| Auth / vault | ✅ PIN (Argon2id) + DPAPI + recovery key, auto-lock, fresh PIN for Tier 3+, secrets vault | `vault.py`, `secrets_store.py` |
| Privacy dashboard | ❌ | Phase 6 |
| Installer | ❌ Python not bundled | Phase 7 |
| Internet | ✅ Egress guard: allowlist / network-tool rule / offline mode, every call logged; tests can't go online | `egress.py` |
| Tests | ✅ 287 pass on Windows + chat smoke + Electron start | `backend/tests/`, `tools/` |

## 2. Phase 0 results (done 2026-09-27)
Verified on Windows with `tools\check.bat`.
- The test suite really runs now (one import error stopped collection; `check()`-style tests printed FAIL but passed). 158/158, and failures fail.
- Tests no longer write into the real memory DB / audit log (`%APPDATA%\sentinel`); every run uses a throwaway data folder.
- Fresh-install crash on the first "remember that…" fixed (FTS index created in `init_db()`, un-indexed rows back-filled).
- Resource governor now leaves HIGH_LOAD/EMERGENCY (counter reset bug), so models load again after a heavy task.
- Production UI no longer blank (Vite asset paths); UI auto-reconnects to the backend.
- `/api/governor/*` require the session token; token checks are constant-time.
- Electron attack surface cut: removed unused renderer powers (launch/kill processes, read directories, capture the screen, change config) and a legacy JS AI engine with a **Google Gemini cloud router**. Sandboxed renderer, navigation/new windows blocked, CSP in place.
- No Google Fonts request at startup any more.
- `.gitattributes`, pinned `requirements.txt`, FastAPI lifespan, live backend logs.

**GPU probe (bundled llama.cpp build 10679 + CUDA 12):** Qwen2.5 1.5B Q4: ~15 tok/s on CPU (current binding) vs **150 tok/s** CUDA · Qwen2.5 7B Q4: **44 tok/s** CUDA (fits in 8 GB VRAM).

## 3. Decisions
- **D1 GPU inference: APPROVED 2026-09-27, built right after Phase 1.** `llama-server.exe` (CUDA) sidecar managed by the backend: 127.0.0.1, random port, per-boot API key, started on load, killed on unload (frees VRAM), binary hash-pinned. Ollama considered, not chosen (always-on service, less control).
- **D2 Test rows in the real memory DB: APPROVED.** A script backs up `jarvis_memory.db`, shows how many test-created rows it found, and deletes only after you confirm. Runs before encryption (step 1.0).
- **D3 GitHub repo was PUBLIC.** History scan on 2026-09-27 (common key formats, passwords, `.env`, DB files) found none, only test placeholder tokens, so nothing to revoke. Owner sets the repo to Private; nothing is pushed until then. Archive `chore/structure-cleanup`.
- **D4 Unlock: PIN now, Windows Hello later (Phase 2).** Random 256-bit data key, wrapped by a PIN-derived key (Argon2id) and by DPAPI (tied to your Windows login). One-time recovery key kept offline.
- **D6 PIN re-check from risk Tier 3 (decided 2026-09-27).** Approving an action that changes files, launches programs or deletes (Tier 3+) needs a PIN typed in the last 5 minutes. Tier 2 (web search, reading approved data) still needs your click but no PIN, because asking for it on every search would be tedious. `PIN_REQUIRED_TIER` in `vault.py` can lower it to 2.
- **D5 Working model: split by risk.** Claude writes all security-critical code; low-risk tasks go to Antigravity/Codex as task cards (`docs/tasks/`, rules in `AGENTS.md`); Claude reviews the diffs. Windows checks run through the watcher (§5).

## 4. Roadmap (smallest secure step first)

### Phase 1: Security foundation ✅ DONE 2026-09-27 (branch `phase1/security`)
Commits: 53d2af0 setup · c48c88e GPU/NVML · 2009943 egress · f871ed8 WS token · 062430f vault + SQLCipher · d992197 review fixes · bb8b9e2 secrets/redaction/retention. An independent review found 11 issues before the owner's data was touched; all fixed (see CHANGELOG).
| Step | What | In plain words |
|---|---|---|
| 1.0 Housekeeping | setup script + watcher · D2 cleanup · governor reads the GPU through NVML (`nvidia-ml-py`) off the event loop instead of spawning `nvidia-smi` | clean start; chat never stalls on GPU polling |
| 1.1 Egress guard | one outbound client: allowlist, per-site approval, log of every call (time, skill, host, size, no content) · tests block non-loopback sockets (`test_research.py` stops hitting the internet) · Electron main blocks non-local requests · "online" indicator in the UI | nothing leaves the PC without you seeing it |
| 1.2 Token out of URL | WebSocket auth by first message/header, not `?token=` | URLs end up in logs |
| 1.3 Owner unlock | D4 key scheme · unlock screen at start · auto-lock when idle · PIN re-check before Tier-2+ actions · attempt rate-limit · recovery key | only you can open Sentinel's data |
| 1.4 Encrypted memory | spike: encrypted-SQLite package for Python 3.14/Windows (SQLCipher or SQLite3 Multiple Ciphers); fallback AES-GCM fields + in-memory search index rebuilt on unlock · migration: backup → encrypt → verify → keep backup until you OK it | the memory file is gibberish without your PIN |
| 1.5 Vault + redaction | secrets live inside the encrypted store · log filter redacts secrets/tokens | keys never sit in files or logs |
| 1.6 Deletion & retention | "forget" removes rows, index entries and old backups per policy · default retention settings | keep only what's needed |

- **New dependencies (pinned):** `cryptography`, `argon2-cffi`, `nvidia-ml-py`, one encrypted-SQLite package. No cloud services, no new models.
- **Risks → safeguards:** migration failure → backup + verify + rollback · forgotten PIN → recovery key · no Python 3.14 wheel → fallback design · egress guard blocks research/downloads → allowlist + approval prompt.
- **Done when:** ✅ the raw DB file has no plaintext and opens only after unlock (tested) · ✅ wrong PIN fails and is rate-limited · ✅ no secret in logs, tests or URLs (tested) · ✅ every outbound call logged and the full suite runs offline · ✅ Tier-3+ actions need a recent PIN (D6) · ✅ all tests + smoke + Electron start pass on Windows · ⏳ the owner's real database migrated (O2).

### Phase 1b: GPU sidecar (D1)
Sidecar manager (start/stop, health check, VRAM-aware via the governor) · 7–8B default model on GPU, 1.5B CPU fallback · hash-pinned binaries · benchmark in `tools\check.bat -Only gpu`.

### Phase 2: Voice & identity
faster-whisper STT (GPU) · openWakeWord ("Hey Sentinel") · SpeechBrain ECAPA voice-print gating sensitive actions, PIN fallback · Windows Hello option (D4) · Piper TTS · no raw audio kept unless opted in · pauses when gaming/on a call.

### Phase 3: Smarter brain
Model refresh · reliable tool calling + multi-step planner with confirmation summary · **prompt-injection defense: web pages, files and messages are data, never instructions; they can't trigger tools, and tool calls after reading untrusted content need confirmation** · local embeddings + encrypted retrieval over your files · "can do now / ~X min / schedule / can't" capability answers.

### Phase 4: System control & automation
File ops with dry-run + undo · app launch/close with confirmation · scheduler + resource-aware background queue · battery/thermal/full-screen/call detection feeding the governor · emergency stop / safe mode / offline mode in the UI.

### Phase 5: Skills
Productivity (calendar, reminders, tasks) · coding assistant · documents · portfolio tracking (read-only first) · research digests · **each skill in its own process with resource quotas, so one crash can't take Sentinel down** · enable/disable/update per skill in the UI. Each skill: manifest + permissions + tests + audit.

### Phase 6: Integrations & privacy dashboard
Email/calendar behind explicit permission, drafts only until approved · dashboard of what data exists, where, what touched it, what went online.

### Phase 7: Hardening & packaging
Installer that bundles Python · hash-pinned model/binary verification · remove unused npm deps (`@huggingface/transformers`, `chokidar`, `electron-store`, `marked`: ~250 MB) · tamper-evident (hash-chained) audit log · encrypted backup/restore · threat model · performance tuning.

## 5. How we work (token-efficient)
- **Claude:** design, security-critical code, reviews. Edits the repo directly through the linked folder (plain text, the cheapest path). Doesn't drive other AIs by screen control (a screenshot costs ~1.5k tokens).
- **Antigravity / Codex:** low-risk task cards in `docs/tasks/` under the rules in `AGENTS.md`. Claude reviews only the diff and the test result.
- **Don't disturb the owner:** `smoke`, `electron` and `quick` stop running Sentinel processes. Don't run them while the owner is using the app; `pytest`/`tests` are safe any time.
- **Watcher (Windows checks without screenshots):** `tools\start_watcher.bat` (first time: `tools\setup_phase1.bat`); leave the window open. Claude writes one word to `docs\runs\request.txt`: `quick | tests | pytest | smoke | electron | env | gpu | all | deps | probe | status | commit | ff-main`. The watcher runs that fixed command and writes `docs\runs\latest.txt` + `watcher_status.txt`. `commit` uses `docs\runs\commit_msg.txt`, never on `main`, never pushes. Claude reads summary lines only.
- **Git:** writes (commit/branch/merge) only on Windows (watcher or scripts). The Linux side uses read-only `git --no-optional-locks`: its shell can't delete files, so a normal `git status` can leave a stale `index.lock`. The owner pushes, and only after the repo is private.
- **Sessions:** one phase per session; this roadmap is the handoff and is updated at the end of each phase.
