# Sentinel: what changed, in plain words

Newest first. Each entry says what changed, why it matters and how to check it.
- Live task status: `docs/TRACKER.md`
- Plan and decisions: `docs/ROADMAP.md`
- Full technical detail: the commit history (`git log`)

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
