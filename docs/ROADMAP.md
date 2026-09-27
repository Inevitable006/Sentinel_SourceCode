# SENTINEL: Assessment & Roadmap
_Living plan. Last updated 2026-09-27 after Phase 0 (stabilize). Tick items off as phases finish._

## 1. Where things stand

**Machine:** i5-12400F (12 threads) · 32 GB RAM · RTX 3050 8 GB · Windows 11 Pro · Python 3.14.3 · Node 24.
**Repo:** `C:\Muthu project\New one\Sentinel_SourceCode` (no longer inside OneDrive).

| Layer | Status | Where |
|---|---|---|
| Desktop shell | ✅ Electron + React/Vite. Production build now loads (was a blank window) | `src/main`, `frontend/` |
| Backend | ✅ FastAPI + WebSocket streaming, cancel, one-request guard, confirmations | `backend/app/main.py` |
| Local LLM | 🟡 Works, but **CPU only** (python binding has no GPU offload). See decision D1 | `ai_service.py` |
| System awareness | ✅ Profiler + resource governor (recovery bug fixed) | `resource_governor.py` |
| Security core | ✅ Policy tiers, single-use confirmation tokens, audit log, sandboxed runner, session token | `policy_engine.py`, `secure_runner.py` |
| Skills | ✅ 7 skills | `backend/skills/` |
| Vision | ✅ Secure image ingest + local inference | `vision_*.py` |
| Memory | 🟡 SQLite + FTS (fresh-install crash fixed). **Not encrypted yet** | `db/`, `memory_service.py` |
| Voice | 🟡 TTS only (pyttsx3) | `voice_service.py` |
| Auth / vault | ❌ | Phase 1 |
| Privacy dashboard | ❌ | Phase 6 |
| Installer | ❌ Python not bundled | Phase 7 |
| Tests | ✅ **158 pass on Windows**, plus end-to-end chat smoke test and Electron start test | `backend/tests/`, `tools/` |

## 2. Phase 0 results (done 2026-09-27)

Verified on Windows with `tools\check.bat` (output in `docs\runs\latest.txt`, not committed).

**Fixed**
- Test suite never really ran under pytest: one import error stopped collection; `check()`-style tests (incl. 22 security tests) printed FAIL but still passed. Now 158/158 pass and a failed check fails the test.
- Tests wrote into your **real** memory DB and audit log (`%APPDATA%\sentinel`). Now every run uses a throwaway data folder.
- Fresh install crashed on the first "remember that…": the memory search index was only created by a manual migration script. Now created at startup (`init_db()`), and any un-indexed memories are back-filled.
- Resource governor never left HIGH_LOAD/EMERGENCY (counter reset bug), so after a game or heavy task Sentinel refused to load a model until restart. Fixed + tests.
- Production UI was blank (Vite asset paths), and the UI gave up if the backend started a second later. Fixed: relative asset paths + auto-reconnect.
- Unauthenticated `/api/governor/*` endpoints now require the session token; token checks are constant-time.
- Electron attack surface cut: the renderer could launch/kill processes, read directories, capture the screen, change config and call a legacy JS AI engine with a **Google Gemini cloud router**. None of it was used by the UI; all removed. Renderer is sandboxed, navigation/new windows are blocked, only the app page can get the session token, and a Content-Security-Policy is in place.
- The UI fetched Google Fonts on every start (outbound request). Removed.
- `.gitattributes` (clean `git status`), pinned `requirements.txt`, FastAPI lifespan, scratch files moved out, backend logs stream live.

**Measured (GPU probe, bundled llama.cpp build 10679 + CUDA 12)**

| Model | Engine | Generation speed |
|---|---|---|
| Qwen2.5 1.5B Q4 | current python binding (CPU) | ~15 tok/s in the app |
| Qwen2.5 1.5B Q4 | llama.cpp CUDA | **150 tok/s** |
| Qwen2.5 7B Q4 | llama.cpp CUDA | **44 tok/s** (fits in 8 GB VRAM) |

## 3. Decisions

- **D1 — GPU inference (needs your OK).** Run the bundled `llama-server.exe` (CUDA) as a sidecar process managed by the backend: bound to 127.0.0.1 on a random port, per-boot API key, started on "load model", killed on "unload" (frees VRAM completely). Benefits: 4–10× faster, 7–8B models become the default, newer model families and vision work. Risks: one more process; binaries must be hash-pinned (Phase 7). Alternatives: build `llama-cpp-python` with CUDA for Python 3.14 (needs CUDA toolkit + Visual Studio, fragile), or use Ollama (always-on service, less control).
- **D2 — Clean test data out of your real memory DB?** Earlier test runs inserted test memories/threads into `%APPDATA%\sentinel\jarvis_memory.db`. A cleanup script can back up the DB and remove only rows created by tests.
- **D3 — GitHub remote** `Inevitable006/Sentinel_SourceCode`: confirm it is private (the project is meant to be personal, and `package.json` says MIT).

## 4. Roadmap (smallest secure step first)

### Phase 1: Security foundation
- Secrets vault: Windows Credential Manager via `keyring` (no keys in files/env)
- Encrypted memory DB (SQLCipher, or AES-GCM fields with a DPAPI-protected key)
- Owner unlock: PIN / Windows Hello at start and before Tier-2+ actions
- Network egress guard: one outbound HTTP client, allowlist + per-request approval + log of every external call; tests must not hit the internet (`test_research.py` does today)
- Move the WebSocket session token out of the URL (uvicorn logs URLs) into a header/first message
- Governor: run `nvidia-smi` off the event loop (it can stall streaming for up to 2 s)
- **Done when:** DB unreadable without unlock, no secret in logs/tests, every outbound call logged.

### Phase 2: Voice & identity
faster-whisper STT (GPU) · openWakeWord ("Hey Sentinel") · SpeechBrain ECAPA voice-print gating sensitive actions, PIN fallback · Piper TTS · no raw audio kept unless opted in · pauses when gaming/on a call.

### Phase 3: Smarter brain
D1 GPU sidecar · model refresh (7–8B default on GPU) · reliable tool calling + multi-step planner with confirmation summary · local embeddings + encrypted retrieval over your files · "can do now / ~X min / schedule / can't" capability answers.

### Phase 4: System control & automation
File ops with dry-run + undo · app launch/close with confirmation · scheduler + resource-aware background queue · emergency stop / safe mode / offline mode in the UI.

### Phase 5: Skills
Productivity (calendar, reminders, tasks) · coding assistant · documents · portfolio tracking (read-only first) · research digests. Each: manifest + permissions + tests + audit.

### Phase 6: Integrations & privacy dashboard
Email/calendar behind explicit permission, drafts only until approved · dashboard of what data exists, where, what touched it, what went online.

### Phase 7: Hardening & packaging
Installer that bundles Python (embedded runtime or PyInstaller sidecar) · hash-pinned model/binary verification · remove unused npm deps (`@huggingface/transformers`, `chokidar`, `electron-store`, `marked`: ~250 MB incl. onnxruntime) · threat model · backup/restore · performance tuning.

## 5. How we work
- Claude does design + code + review; one phase at a time; each phase ends with tests + a milestone note.
- Windows-side verification: `tools\check_quick.bat` (tests + chat smoke + Electron start) or `tools\check.bat` (adds env + GPU benchmark). Results land in `docs\runs\latest.txt`; Claude reads only that file.
- Work happens on a branch per phase (`phase0/stabilize`, …); merge to `main` when green.
