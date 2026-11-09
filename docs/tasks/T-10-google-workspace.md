# T-10: Gmail and Google Calendar connection

Owner selected Gmail and Google Calendar on 2026-10-17 as part of completing the roadmap.

- Branch: `phase1/security`; preserve pending changes; no pushes.
- Files: new Google integration service, authenticated local routes under Workspace, Settings component, integration tests and documentation. Existing vault, PIN, session and egress implementations are reused, not weakened.
- Desktop OAuth uses a random loopback port, state, PKCE S256 and a five-minute timeout; lock/disconnect invalidates pending or in-flight results. Credentials and tokens use the encrypted secrets store. Tokens never return to the renderer.
- Owner imports desktop OAuth credentials in Settings and signs in using their browser. Only Gmail read-only and Calendar events read-only scopes. Refresh buttons perform explicit reads; drafts remain local. No background sync, send, delete or event-write endpoints in this scope.
- Outbound OAuth and reads use SafeAsyncClient and an explicit Google operation context; no allowlist expansion, redirects or new dependencies. Offline mode remains enforced. Browser sign-in is an explicit owner action outside Sentinel's HTTP client.
- Acceptance: mocked provider responses, real loopback callback, bad state/replay, insufficient scope, expiry, lock race, offline mode, auth/PIN and secret non-disclosure checks; frontend/full regression. Live provider consent requires owner setup and must not be claimed without verification.
- Sources: https://developers.google.com/identity/protocols/oauth2/native-app ; https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list ; https://developers.google.com/workspace/calendar/api/v3/reference/events/list

## Report
Implemented backend service/routes and Settings UI. Added eight integration tests covering a real loopback callback with a mocked provider, state/replay/expiry, PKCE, token refresh, partial grants, result bounds, offline-before-DNS, lock-generation invalidation and session/unlock/PIN controls. The first run had a teardown fixture still simulating a locked vault; fixture cleanup now restores its simulated unlocked state before deleting test secrets.

Full regression: `572 passed in 28.64s`; 13 memory checks, 17 JavaScript checks, frontend build and Electron syntax checks passed (`docs/runs/check_20261017_163604.txt`). The later workspace status-refresh UI also passed typecheck/build. Packaged Python loads the backend and Google routes with isolated data. Live Google consent remains unverified because owner credentials and sign-in are required. Setup: `docs/GOOGLE.md`.
