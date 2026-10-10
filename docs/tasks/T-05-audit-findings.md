# T-05: Fix the 10 Oct 2026 audit findings (F01–F23)

Owner instruction, 2026-10-10: fix all findings in `output/pdf/Sentinel_Project_Analysis_Report.md`. Work on `phase1/security`, preserve existing uncommitted changes, no commits or pushes unless the owner asks.

## Scope and permitted files

The owner explicitly authorises changes to security-critical code where a finding requires it: `backend/app/main.py`, `core/secure_runner`, `token_service`, `safe_process`, `network_utils`, `skill_verifier`, `audit_logger`, `redaction`, `secrets_store`, `src/main/main.js`, `src/main/preload.js`. Each change must keep or strengthen the existing boundary (PIN, egress guard, single-use tokens, allowlists). No new dependencies, no new network paths, no machine-security changes. Model/runtime downloads need separate owner approval.

## Order (each milestone ends with the full regression suite green)

A. Honest baseline: F03 structured tool results, F02 unavailable execution skills, F04 real speech readiness, F17 safe mode, F20 status labels, F22 workspace root.
B. Journeys: F01/F18 workspace router + screens, skill switches enforced, F21 continuity.
C. Execution: F09 job identity, F10 atomic tokens, F12 streaming caps, F11 pinned connect, F07 release verifier, F08 worker isolation.
D. Voice/vision: F04 model, F05 image ingest, F15 speech stop on lock, F16 OS lock.
E. F13/F14 prompts, F19 audit, F06 packaging, F23 docs.

Each finding's "Acceptance" paragraph in the report is its test specification.

## Report

Baseline 2026-10-10: `pytest tests` 344 passed.

Result 2026-10-10 (`tools\check.bat -Only tests`, `-Only smoke`, `-Only electron`): **420 backend tests passed**, 13/13 memory checks, frontend build, main/preload syntax, 17/17 JavaScript tests, real Qwen 2.5 7B GPU chat smoke PASS (no llama-server left running), Electron start PASS (exit 0). Nothing committed.

| Finding | Done | How it is tested |
| --- | --- | --- |
| F01 workspace | Router registered; Workspace / Memory / Security screens | `tests/integration/test_workspace.py` |
| F02 coding/Blender | Python runs in contained runner (`python_sandbox.py`); Blender fails honestly | `tests/skills/test_python_coding.py` (real process) |
| F03 false success | `ToolFailure` marker → status=error everywhere | `tests/core/test_tool_failures.py` |
| F04 speech readiness | Status loads the model; smoke no longer uses PyAV | `tests/core/test_speech_input.py` — **model still missing vocabulary file** |
| F05 vision in chat | Upload → memory-only inbox → analysis in chat | `tests/integration/test_vision_attach.py` — **no LLaVA files installed** |
| F06 packaging | Portable runtime path, dev venv excluded, `tools/build_runtime.ps1` | `tools/tests/packaging.test.mjs` — **runtime not built, clean install not done** |
| F07 integrity | Pinned hashes, release policy default, verified bytes executed | `tests/security/test_skill_integrity.py` |
| F08 sandbox/switches | Switches enforced centrally; Python isolated in its own process | `test_workspace.py`, `test_python_coding.py` — other built-in skills still run in-process |
| F09 cancel identity | Context job id; network tasks cancelled too | `tests/security/test_cancel_identity.py` |
| F10 atomic tokens | Lock around validate+consume | `tests/security/test_token_atomic.py` |
| F11 DNS pinning | Pinned network backend, TLS on real hostname | `tests/security/test_dns_pinning.py` + live check |
| F12 byte limits | Streaming caps for processes and HTTP | `test_cancel_identity.py`, `test_dns_pinning.py` |
| F13/F14 prompts | `prompting.py`, per-family templates | `tests/core/test_prompting.py` |
| F15 speech stop | `VoiceService.stop()` on lock / emergency / Voice off | `tests/core/test_voice_stop.py` |
| F16 OS lock | Electron powerMonitor → `/api/lock` | `tools/tests/os-lock.test.mjs` — **manual lock/sleep test still recommended** |
| F17 safe mode | Public `enterSafeMode`, spawn errors handled, UI notice | `tools/tests/safe-mode.test.mjs` |
| F18 plan recovery | Edit endpoint, interrupted state, background reminders | `test_workspace.py` |
| F19 audit | HMAC chain, rotation, sanitized lines, redaction cleared at lock | `tests/security/test_audit_integrity.py` |
| F20 labels | Backend model state, "Allowed (idle)", data hidden when unverified | frontend build (no UI test harness) |
| F21 continuity | Chat stays mounted, resume thread, retry, code blocks | `tests/integration/test_chat_resume.py` |
| F22 workspace root | `SENTINEL_WORKSPACE` / project folder | `tests/core/test_workspace_root.py` |
| F23 docs/hygiene | Versions aligned (1.0.0), stale Ollama hints removed, 4 unused npm deps removed, `docs/CAPABILITIES.md` | — |

Also fixed: `check.ps1` always reported Electron as failed (empty ExitCode), present since September.
Developers who edit a skill must re-run `tools/pin_skills.py`, or set `SENTINEL_SKILL_DEV=1` while iterating.
