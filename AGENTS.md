# Rules for AI coding agents working on Sentinel

Sentinel is a private, local-first personal assistant for ONE owner: Electron + React UI (`src/main`, `frontend/`) and a Python FastAPI backend (`backend/`). Privacy and system stability come before features.

## Before you start
- Read `docs/ROADMAP.md` (current phase and decisions) and your task card in `docs/tasks/`.
- Do only what the task card asks. If something is unclear or looks wrong, stop and write your question in the card's Report section instead of guessing.

## Hard rules
1. **No new network calls.** Never add code that contacts the internet: HTTP, sockets, CDNs, web fonts, telemetry, cloud AI APIs. All outbound traffic goes through the backend's egress guard. The UI talks only to the local backend.
2. **No new dependencies** (pip or npm) unless the task card lists them, pinned to an exact version.
3. **No secrets or personal data** in code, tests, fixtures, logs or URLs: no API keys, tokens, passwords, real names or real file paths.
4. **Don't touch security-critical code** unless the task card says so:
   - `backend/app/main.py` (auth and session handling)
   - `backend/app/core/`: `policy_engine`, `secure_runner`, `token_service`, `safe_process`, `audit_logger`, `network_utils`, `paths`, `skill_verifier`, and any egress / vault / crypto / unlock module
   - `src/main/main.js`, `src/main/preload.js`, the Content-Security-Policy
5. **Tests are the contract.** Never weaken, skip or delete a test to make it pass. Tests must not touch the real data folder (`%APPDATA%\sentinel`) or the internet.
6. **Don't fake success.** If something fails, say so in the report and include the error.
7. **Git:** work on the branch named in the task card. Never commit to `main`. Never push.

## Checking your work (Windows)
- `tools\check.bat -Only tests`: backend tests + frontend build
- `tools\check_quick.bat`: tests + chat smoke test + Electron start
- Results: `docs\runs\latest.txt`
- Finish by filling in the Report section of the task card: files changed, the test result line, anything left undone.
