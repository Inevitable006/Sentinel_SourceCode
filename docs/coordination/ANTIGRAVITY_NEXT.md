# AntiGravity next queue — 2026-11-02

The previous six-hour transfer is complete. Codex accepted broker/check-script ownership back and is fixing broker review findings. Do not edit any backend or tools/check.ps1 files. A4 remains WAITING. Continue the following tasks without a new prompt at each boundary; stop after this queue.

## A8: Correct owner acceptance claims

Allowed edits: docs/OWNER_ACCEPTANCE.md and docs/USER_QUICKSTART.md; your status file. Review every technical assertion against actual source, not earlier reports. Concrete findings already observed:
- OWNER_ACCEPTANCE claims PBKDF2 checks; the vault uses Argon2id. Avoid implementation claims the owner does not need, or cite the actual mechanism accurately.
- Recovery key is described as hexadecimal; vault format_recovery_key uses base32. Tell the owner to copy the key exactly as displayed rather than inventing a format.
- Seeing a lock screen is not proof of database closure/key erasure. Separate observable UI behavior from backend automated evidence; do not promise memory zeroing.
- Typed-chat cancellation says immediate; distinguish acknowledgement from bounded process/model shutdown and do not promise zero latency.
- Use fresh-PIN wording consistently: a recent verification can avoid another prompt. The checklist must not fail simply because it reused a fresh PIN.
- Avoid stale undated test totals. Link dated checkpoint reports rather than embedding counts that change with each backend increment.

Check remaining labels and claimed evidence similarly. Preserve safe isolated-restore guidance. Do not require owner credentials or run actions against the owner's profile. Report exact corrections and unresolved claims.

## A9: Real rendered settings verification, if tooling permits

Allowed edits: existing A1/A2 settings components and ReadinessPanel.css for demonstrated usability defects only; optionally one temporary-development fixture at frontend/tests/settings-preview.tsx and frontend/settings-preview.html. No shared CSS, production entrypoint, package/dependency or backend changes. Do not put fixtures in the shipped bundle or replace actual API helpers in production.

Use synthetic responses and existing tooling to inspect rendered loading, ready, unknown, failed, PIN-required and cancelled states. Verify keyboard focus/Enter handling, labels and 320/375px narrow layouts. In particular minmax(260px,1fr) is not proof a panel fits inside a narrow container with padding: measure/inspect actual overflow. Never claim a build or hook adapter is browser evidence. No real Google OAuth, microphone capture, real backups or app data.

If safe browser tooling/fixtures are unavailable, record NOT_VERIFIED and finish independent A8; do not install another framework or fabricate screenshots/results. If a fixture is added, keep it unreferenced by the production entrypoint and verify it is absent from production build output. Fix only observed issues, run relevant existing settings/readiness tests and one frontend build. Record viewport, exercised states, commands and evidence in ANTIGRAVITY_STATUS.md.

Check CODEX_STATUS for build reservation before building. Retain ownership of frontend/docs; do not re-edit the handed-back broker. Report READY_FOR_REVIEW or QUEUE_EXHAUSTED with unverified items. Do not start voice UI or invent extra features.
