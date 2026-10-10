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
| File actions | Works | Create, edit, move, delete inside Documents\Sentinel Workspace only (SENTINEL_FILES to change). Preview on the approval card, refused if the file changed after approval, Undo for 5 minutes (Workspace → File actions), then final. Deleted files are held until the window closes. |
| Document reading | Works | Text files in the project or Sentinel data folder only. |
| Image analysis | Needs model files | Attach → validated → analyzed in memory. Without local LLaVA files the chat says the image could not be analyzed. |
| Dictation | Needs model file | Shows unavailable until the Whisper model loads; vocabulary file missing (docs/VOICE.md). |
| Speech output | Works, not heard in tests | Choose a male or female Windows voice (David / Zira on this PC) and speed in Settings → Voice, with Preview; saved for next time. Stops on lock, emergency stop and Voice off. |
| Portfolio Advisor | Works (advice only) | Import holdings (Zerodha/Groww/CAMS CSV) or add by hand; value, gain, mix; fund NAVs (AMFI) and NSE prices when you press Refresh; suggestions with reasons and steps; SIP/lumpsum ranges; ask about it in chat. Never logs in or trades. |
| Daily briefing | Works | "Today" screen (opens first): reminders due today (local time) and overdue, plans needing you, portfolio change since the previous price refresh, PC health, backup age; Read aloud. Read-only. |
| Encrypted backup | Works | Settings → Backup: one .sentinelbak file, still encrypted; opens with your PIN on this PC or your recovery key anywhere. Restore from the lock screen: checked first, current data kept aside. Last 5 kept locally. |
| System Watch | Works | Every 15 min + Check now: startup items, scheduled tasks, services, admin accounts, firewall, Defender and threats, programs running from Downloads/Temp, Sentinel's own files. Alerts with steps; only automatic reaction is Offline mode on a critical alert. Not an antivirus. |
| What Sentinel did | Works | Security → What Sentinel did: every action in plain words (from chat/plan, approved or not, done/failed/blocked), filters, last 1/7/30 days, plus the audit-log integrity check. No search terms or file contents recorded. |
| Lock | Works | Manual, idle timeout, Windows lock and sleep (Electron powerMonitor; manual check recommended). UI hides data when lock state cannot be confirmed. |
| Skill integrity | Works | Pinned SHA-256 per built-in skill checked at registration and load; development mode only with SENTINEL_SKILL_DEV=1. Re-pin with `tools/pin_skills.py`. |
| Audit log | Works | HMAC-chained entries (DPAPI-protected key), tamper detection, 5 MB rotation, sanitized errors. Detects tampering; cannot prevent it by a process running as you. |
| Installer | Needs owner steps | `tools/build_runtime.ps1` builds the portable runtime from files you download; then `npm run dist`. Clean-machine install not yet verified. |

Not implemented (from the NEXUS idea): biometrics/Windows Hello, wake word, vector memory, multi-user, cross-device sync, creative media, health, OS-wide security monitoring.
