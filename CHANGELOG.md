# Sentinel: what changed, in plain words

Newest first. Each entry says what changed, why it matters and how to check it.
- Live task status: `docs/TRACKER.md`
- Plan and decisions: `docs/ROADMAP.md`
- Full technical detail: the commit history (`git log`)

---

## 2026-09-27 · Steps 1.3 + 1.4: your PIN, and an encrypted database
**Branch:** `phase1/security`

- **What changed:** Sentinel's memories, chats and settings now live in an **encrypted database** (`%APPDATA%\sentinel\sentinel.db`, SQLCipher). It stays closed until you unlock Sentinel with your **PIN**. While it's locked, nothing can read it: not the app, not another program, not someone who copies the file.
- **First start:** Sentinel asks you to choose a PIN (6+ characters; a longer passphrase is stronger). It then shows a **recovery key** once, for example `ABCD-EFGH-…`. Save that key on paper or in a password manager. If you forget your PIN, or Windows is reinstalled, it's the only way back in. Nobody can reset the PIN for you, by design.
- **Your existing data moves over by itself:** at setup, the old unencrypted database (`jarvis_memory.db`) is copied into the encrypted one. It's checked table by table and cleaned of rows left behind by old test runs: four known test memories, one test chat and empty chat sessions. The old file stays untouched until you delete it in **Settings → Security**.
- **How the keys work, in short:** a random 256-bit key encrypts the database. That key is stored only in locked form, twice:
  - with your PIN (Argon2id, deliberately slow to guess) and then sealed by Windows DPAPI, so it also needs your Windows login;
  - with your recovery key.
  `keystore.json` contains only those locked copies.
- **Guessing is slowed down:** after 5 wrong PINs you wait 30 seconds, then 60, 120… up to an hour. This survives restarts.
- **Auto-lock:** Sentinel locks after 15 idle minutes (change it in Settings, or pick "Never"). The **Lock Sentinel** button in the sidebar locks it at once. Locking closes the database, including connections already in use, and tells open chat windows.
- **PIN for risky actions:** approving something that changes files, launches programs or deletes (risk Tier 3+) asks for your PIN again if you haven't typed it in the last 5 minutes (decision D6).
- **Also:** the sidebar's fake "System Online" label is replaced by the Lock button. Settings gained Change PIN, auto-lock and "delete old unencrypted copy".
- **New packages:** `cryptography 50.0.1` (AES-GCM, Argon2id) and `sqlcipher3-wheels 0.5.7` (encrypted SQLite). Both were checked on your Python 3.14 first. Neither makes network calls.
- **Tests:** 237 pass. They cover the vault (rate limits, recovery, auto-lock, Windows binding), the encrypted file (no plaintext on disk, wrong key refused, locked means closed) and the migration (verify, clean, keep the old file). The chat smoke test now sets up a PIN in an isolated folder first.
- **Files:** `backend/app/core/vault.py` (new), `app/core/dpapi.py` (new), `app/db/database.py` (rewritten), `app/main.py` (unlock API, 423 while locked, auto-lock loop), tests (`test_vault.py`, `test_database_encryption.py`, `test_unlock_api.py`, `test_crypto_capabilities.py`, plus updates), `tools/smoke_chat.py`, `frontend/src/components/Unlock/*` (new), `App.tsx`, `Sidebar`, `ChatArea.tsx`, `SettingsPanel.tsx`, `lib/backend.ts`

---

## 2026-09-27 · Step 1.2: session token out of URLs
**Branch:** `phase1/security`

- **What changed:** the chat connection between the window and the backend used to carry the per-boot session password in its web address (`/ws/chat?token=…`). The backend's log writes every address it sees, so the password landed in log files. It now travels in a connection header (the WebSocket "subprotocol"), and the address is just `/ws/chat`.
- **Still refused before it opens:** a wrong or missing token still gets the connection refused before anything is exchanged. A token in the address is now ignored on purpose.
- **How to check:** in `docs\runs\latest.txt` after `tools\check_quick.bat`, the backend log shows `"WebSocket /ws/chat" [accepted]` with no token.
- **Tests:** 193 pass, including new ones for header-only tokens, tokens in the URL being ignored, and malformed headers. The real chat smoke test and the desktop app both connect the new way.
- **Files:** `backend/app/main.py`, `frontend/src/components/Chat/ChatArea.tsx`, `tools/smoke_chat.py`, `tests/security/test_api_auth.py`, `tests/integration/test_chat_protocol.py`, `test_reliability.py`, `test_phase_v1_vision.py`, `tests/security/test_phase9_security.py`

---

## 2026-09-27 · Step 1.1: the internet gate
**Branch:** `phase1/security`

- **What changed:** every internet request from Sentinel now goes through one gate, the egress guard. A request is allowed only if its site is on a short allowlist (DuckDuckGo search, Yahoo market data) or it comes from a tool that declared it needs the internet. Those tools already pass the policy check and, for higher-risk ones, your confirmation. Everything else is blocked, and blocked sites are not even looked up in DNS.
- **Offline mode:** a new switch in **Settings → Privacy & Constraints** blocks all internet access, web search included. It's remembered across restarts. If the setting file is ever damaged, Sentinel stays offline rather than guessing.
- **What went online:** every decision (allowed or blocked) is written to `%APPDATA%\sentinel\logs\egress.jsonl`, and the latest ones appear in Settings. The log keeps only the site, tool, time, status and size, never the page path or what you searched for.
- **Desktop app:** the Electron window itself can now only talk to your PC (the local backend and its own files). Any other request is cancelled and logged. This is a second layer on top of the existing Content Security Policy.
- **Live telemetry:** the right-hand panel used to show made-up numbers ("Qwen-1.5B", "4.2 / 16.0 GB", "21 ms"). It now shows real CPU, RAM, GPU, model, engine and internet status from the backend every 5 seconds, and says "Backend not reachable" instead of inventing values.
- **Honest labels:** the Settings button called "Clear Personal Memory" only ever cleared research history, so it's now called "Clear Research History". A real "forget all memories" comes in step 1.6.
- **Bug fixed:** web searches containing `&` or `#` were cut short because the query wasn't URL-encoded.
- **Tests can't use the internet any more:** any test that tries is stopped. This caught 5 tests that had been quietly doing real DNS lookups; they now use a fake answer.
- **Tests:** 190 backend tests pass, the UI builds, and the desktop app starts cleanly with the gate on.
- **Files:** `backend/app/core/egress.py` (new), `network_utils.py`, `secure_runner.py`, `research_service.py`, `resource_governor.py`, `main.py` (`/api/egress/status`, `/api/egress/log`, `/api/egress/offline`), `tests/conftest.py`, `tests/security/test_egress.py` (new), research/finance/web tests, `src/main/main.js`, `frontend/src/lib/backend.ts` (new), `SystemStatus.tsx/.css`, `SettingsPanel.tsx/.css`

---

## 2026-09-27 · Step 1.0: GPU readings without stalls
**Branch:** `phase1/security`

- **What changed:** Sentinel now reads your GPU (memory, load, temperature) through NVIDIA's own library, NVML, inside the backend. It no longer starts an `nvidia-smi` program every 5 seconds. One reading is shared by every part of the app for 2 seconds, and it's taken off the main loop.
- **Why it matters:** each `nvidia-smi` start could freeze chat streaming for up to 2 seconds. A reading now takes under a millisecond. If NVML is missing, Sentinel falls back to a single `nvidia-smi` call. With no NVIDIA GPU at all, it quietly reports "no GPU" and tries again a minute later instead of on every poll.
- **Also new:** the system status now includes GPU details. The watcher gained `pytest` (fast backend tests) and `probe` (checks which packages have ready-made Windows wheels). It now opens minimized, can't be frozen by a stray click, and writes a heartbeat.
- **New package:** `nvidia-ml-py 13.615.71`, NVIDIA's official Python binding. It makes no network calls.
- **Tests:** 174 pass on your PC, including one that reads your real RTX 3050.
- **Files:** `backend/app/core/gpu_monitor.py` (new), `resource_governor.py`, `skill_router.py`, `requirements.txt`, `tests/core/test_gpu_monitor.py` (new), `tests/core/test_resource_governor.py`, `tools/check.ps1`, `tools/watch_checks.ps1`, `tools/start_watcher.bat`

---

## 2026-09-27 · Phase 1 setup
**Branch:** `phase1/security`

- **Check watcher** (`tools\watch_checks.ps1`; start it with `tools\start_watcher.bat`). Claude can now run the Windows test checks and make local commits without screenshots. It runs only a fixed list of commands (`quick`, `tests`, `smoke`, `electron`, `env`, `gpu`, `all`, `deps`, `status`, `commit`). It never pushes to GitHub and never commits on `main`. When the script itself changes, the watcher checks the new version for syntax errors and restarts with it. Close its window to stop it.
- **`deps` check.** Installs the pinned Python packages from `backend\requirements.txt` into `backend\.venv`, then runs `pip check`.
- **One-click setup** (`tools\setup_phase1.bat`). Moves `main` up to the finished Phase 0 work and opens the `phase1/security` branch.
- **Rules for AI helpers** (`AGENTS.md`) and **task cards** (`docs/tasks/`). These say what Antigravity or Codex may and may not touch: no new internet calls, no new packages, no security files, never weaken tests, never push.
- **Tracker** (`docs/TRACKER.md`) and **this file**, so every change is written down in plain language.
- **Roadmap** (`docs/ROADMAP.md`) updated with the approved Phase 1 plan and decisions D1–D5.

---

## 2026-09-27 · Phase 0: stabilize
**Branch:** `phase0/stabilize` · verified on Windows: 158 tests, chat smoke test and Electron start all pass.

| What was wrong | What changed |
|---|---|
| The test suite never really ran. One import error stopped it, and 22 security checks printed FAIL but still "passed". | 158 real tests now run, and a failed check fails the run. |
| Test runs wrote into your real memory database and audit log (`%APPDATA%\sentinel`). | Every test run now uses a throwaway folder. |
| On a fresh install, the first "remember that…" crashed. | The memory search index is created at startup, and older memories are indexed automatically. |
| After a game or a heavy task, Sentinel refused to load a model until you restarted it. | The resource governor now recovers once the load drops. |
| The installed app showed a blank window, and gave up if the backend started a second late. | Asset paths fixed; the UI reconnects automatically. |
| Some system-monitor endpoints answered without the session password. | They now require the session token, checked in constant time. |
| The app window had powers it never used: starting and killing programs, reading folders, capturing the screen, changing settings. It also contained a hidden path to Google's Gemini cloud AI. | All removed. The window is sandboxed, only the app's own page gets the session token, and a Content Security Policy blocks everything else. |
| Google Fonts were downloaded at every start, an internet request you never asked for. | Removed. |
| Mixed line endings, unpinned packages, noisy startup. | Consistent line endings, pinned Python packages, clean startup and shutdown, live backend logs. |

**GPU test:** with CUDA, the same 1.5B model answers at about 150 tokens/s instead of about 15 on the CPU, and a 7B model runs at about 44 tokens/s on your RTX 3050. This is the basis for decision D1.

**How to check:** run `tools\check_quick.bat`. Then open `docs\runs\latest.txt`: it should show `158 passed` and `SMOKE RESULT: PASS`.
