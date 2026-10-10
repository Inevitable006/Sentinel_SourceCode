# What Sentinel can do (tested snapshot, 2026-10-10)

The single authoritative list. "Works" means exercised by automated tests on this snapshot; anything needing hardware, model files or a manual check says so. Not listed = not implemented.

| Area | State | Notes |
| --- | --- | --- |
| Typed local chat | Works | Real Qwen 2.5 7B GPU chat smoke; correct chat template per model (ChatML for Qwen, Llama 3 format for Llama); instructions always present, memories added as untrusted data. |
| Tool approvals | Works | Every model tool call needs approval; Tier 3+ needs a fresh PIN; single-use tokens are atomic; failures are reported as failures. |
| Cancellation | Works | Stop cancels the request's own processes and network calls, including approved actions. |
| Workspace | Works | Tasks with reminders, plans (step-by-step approval, interruption recovery), email/calendar/document drafts (never sent), memory, history with "continue conversation", privacy view, skill switches, emergency stop. |
| Python coding skill | Works, contained | Separate isolated process, job-object memory cap, no network/processes/native code, files only in the Sentinel Python workspace, 20 s limit. Not a sandbox for hostile code. |
| Blender skill | Unavailable | Blender cannot be contained the same way; calls fail with an error. |
| Web research / finance quote | Works (network) | Through the egress guard; connections pinned to the validated address; 2 MB response limit. |
| Document reading | Works | Text files in the project or Sentinel data folder only. |
| Image analysis | Needs model files | Attach → validated → analyzed in memory. Without local LLaVA files the chat says the image could not be analyzed. |
| Dictation | Needs model file | Shows unavailable until the Whisper model loads; vocabulary file missing (docs/VOICE.md). |
| Speech output | Works, not heard in tests | Stops on lock, emergency stop and Voice off. |
| System Watch | Works | Every 15 min + Check now: startup items, scheduled tasks, services, admin accounts, firewall, Defender and threats, programs running from Downloads/Temp, Sentinel's own files. Alerts with steps; only automatic reaction is Offline mode on a critical alert. Not an antivirus. |
| Lock | Works | Manual, idle timeout, Windows lock and sleep (Electron powerMonitor; manual check recommended). UI hides data when lock state cannot be confirmed. |
| Skill integrity | Works | Pinned SHA-256 per built-in skill checked at registration and load; development mode only with SENTINEL_SKILL_DEV=1. Re-pin with `tools/pin_skills.py`. |
| Audit log | Works | HMAC-chained entries (DPAPI-protected key), tamper detection, 5 MB rotation, sanitized errors. Detects tampering; cannot prevent it by a process running as you. |
| Installer | Needs owner steps | `tools/build_runtime.ps1` builds the portable runtime from files you download; then `npm run dist`. Clean-machine install not yet verified. |

Not implemented (from the NEXUS idea): biometrics/Windows Hello, wake word, vector memory, multi-user, cross-device sync, creative media, health, portfolio analytics, OS-wide security monitoring.
