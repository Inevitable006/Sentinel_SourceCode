# Project structure

★ = security-critical (see AGENTS.md: change only when a task card allows it).

```
Sentinel_SourceCode/
├─ AGENTS.md, CHANGELOG.md        rules for AI agents · change history
├─ package.json                   Electron app + installer config (electron-builder)
├─ src/main/                      Electron (desktop shell)
│  ├─ main.js ★                   window, starts the Python backend, session token, OS lock → Sentinel lock
│  ├─ preload.js ★                the only bridge the UI gets (token, port, lock/fatal notices)
│  └─ core/                       logger, config, error handler (safe mode), hardware profiler
├─ frontend/                      React UI (Vite + TypeScript)
│  └─ src/
│     ├─ lib/backend.ts           authenticated calls to the local backend
│     └─ components/
│        ├─ Unlock/               PIN gate (nothing private shows while locked or unverified)
│        ├─ Chat/                 chat, approvals, dictation, image attach
│        ├─ Workspace/            tasks/plans/drafts, Memory+History, Security (privacy, skills, emergency stop)
│        ├─ Settings/, SystemStatus/, Sidebar/, Layout/
├─ backend/                       Python FastAPI backend
│  ├─ run_server.py               entry point
│  ├─ app/main.py ★               HTTP + chat WebSocket, auth, approvals
│  ├─ app/workspace_routes.py     tasks, plans, drafts, memory, history, skills, emergency stop
│  ├─ app/speech_routes.py, vision_routes.py   dictation and image attachment
│  ├─ app/db/                     SQLCipher database + models
│  ├─ app/core/
│  │  ├─ vault.py, dpapi.py ★     PIN, recovery key, encryption keys
│  │  ├─ policy_engine.py, secure_runner.py, token_service.py ★   approvals and tool execution
│  │  ├─ safe_process.py, python_sandbox.py, sandbox_boot.py ★     contained processes
│  │  ├─ egress.py, network_utils.py ★   internet guard, DNS pinning, size limits
│  │  ├─ skill_router/loader/verifier/manifest ★   skills + integrity pins
│  │  ├─ audit_logger.py, redaction.py ★   tamper-evident log, secret masking
│  │  ├─ ai_service.py, prompting.py, llama_sidecar.py, model_registry.py   local model
│  │  ├─ memory_service.py, research_service.py, retention.py, secrets_store.py
│  │  └─ resource_governor.py, gpu_monitor.py, speech_input.py, voice_service.py, vision_*.py
│  ├─ skills/<name>/__init__.py   7 built-in skills (hashes in skill-hashes.json)
│  ├─ scripts/                    model download helpers
│  ├─ tests/                      core / integration / security / skills (pytest)
│  └─ requirements*.txt, speech-model.json, llama-bin.sha256.json, skill-hashes.json
├─ tools/                         check.bat/ps1 (all tests), smoke tests, watcher, pin_skills.py,
│                                 build_runtime.ps1, tests/*.mjs (JavaScript checks)
└─ docs/                          ROADMAP, CAPABILITIES (what works), TRACKER, VOICE, STRUCTURE,
                                  tasks/ (task cards), runs/ (test logs), archive/ (old reports)
```

Not in git (generated or large): `backend/.venv`, `node_modules`, `frontend/dist`, `backend/llama-bin*`, `backend/models`, `build/`, `dist/`, caches.
