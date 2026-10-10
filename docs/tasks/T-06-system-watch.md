# T-06: System Watch

Owner instruction, 2026-10-10: Sentinel should notice when something on the PC is off, tell the owner, and suggest safe steps. It must not claim to be unhackable. Branch `phase1/security`, no commits unless asked.

## Scope
- Read-only checks using built-in Windows tools only (PowerShell cmdlets, `psutil`); no new dependencies, no network calls.
- Baseline stored in the encrypted database; alerts stored there too.
- Checks: Defender status and recent detections, startup items (Run keys, Startup folder), scheduled tasks, services, local administrators, firewall profiles, processes running from Downloads/Temp, unknown processes with outbound connections, Sentinel self-integrity (skill hashes, GPU engine manifest, audit chain).
- Reactions: automatic only if reversible (Sentinel Offline mode, lock Sentinel). Everything else (Defender quick scan, removing a startup item) is a suggestion or an owner-approved action.
- UI: Security screen shows health, alerts with steps, "this is fine" (accept into baseline), "check now".

## Acceptance
- A new startup item / admin account / service / firewall-off / Defender-off appears as an alert with steps (tests use fixtures, not real system changes).
- Accepting an alert adds it to the baseline and it does not repeat.
- Self-integrity failure raises a critical alert.
- Checks run off the event loop, are rate-limited, and pause when the governor reports high load.
- Nothing is deleted, killed or reconfigured without the owner.

## Report
2026-10-10: implemented. `app/core/system_watch.py` (collector, pure `analyze()`, store), `app/watch_routes.py`, `SystemWatchPanel.tsx` on the Security screen, checks every 15 min in the background loop (skipped under high load). Tests: `tests/security/test_system_watch.py` (18, fixtures only). Full run: 438 backend tests, frontend build, JS checks and Electron start pass. A real collection on this PC takes about 5 s and found nothing wrong (Defender on, signatures current, firewall on, no threats).
Limits: the first run accepts what is already installed as normal; it cannot judge pre-existing infections — that is what the Defender scan button is for.
