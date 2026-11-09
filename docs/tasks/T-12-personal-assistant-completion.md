# T-12: Personal assistant completion

Owner instruction 2026-10-25: complete all phases, add necessary personal-assistant capabilities, avoid unnecessary code. Preserve staged changes and existing safety boundaries; do not commit or push.

First implementation: local semantic document retrieval on top of T-11, with encrypted chunk vectors, transactional invalidation, resource/lock cancellation, bounded explicit indexing, search modes and honest setup status. Reuse llama-cpp-python 0.2.60 already pinned. No new Python/npm dependency.

Model setup authorized by the full-project request: CompendiumLabs/bge-small-en-v1.5-gguf revision d32f8c040ea3b516330eeb75b72bcc2d3a780ab7, bge-small-en-v1.5-q8_0.gguf, 36,806,944 bytes, SHA-256 ec38e8da142596baa913124ae50550de284b6916bf59577ef2f0cb9660c2f514. Fetch only public model bytes during setup; verify before loading; never upload documents. Runtime never downloads models. Source and model license must be documented.

Allowed changes: document retrieval/schema/router/skill/UI/tests, model manifest and setup helper, packaging resource for this small model, completion documentation. Vault callback registration may be used without changing encryption/authentication. Every additional phase must have concrete design and checks before it is marked complete. Personalization, consent, source visibility, cancellation, offline behavior, backups and onboarding are acceptance concerns, not reasons to add duplicate frameworks.

## Report
Semantic retrieval implemented: pinned native English embedding model, encrypted chunk/schema and invalidation triggers, explicit one-document indexing, lock/resource/cancel checks, stale-source rejection, coverage status, keyword/meaning UI and confirmed chat search. Existing staged changes preserved; only the document skill pin changed from the staged baseline.

Verified 2026-10-25: native offline model smoke exit 0 (relevant 0.811 vs unrelated 0.329); frontend typecheck/build; Python compile; packaging structure checks 2/2; in-memory schema/invalidation syntax smoke. None substitute for encrypted integration testing.

Blocked: all 17 selected encrypted integration tests fail at shared setup because Windows Application Control blocks sqlcipher3/_sqlite3.cp314-win_amd64.pyd. Import reports "An Application Control policy has blocked this file." SHA-256 5c05dc24da3e5cb456714b3221130d80bd1963429221882851fed9b411608058 matches the installed wheel RECORD. Owner is arranging approval; no Windows security settings were changed. The 619-test regression pass is historical, before these semantic changes.

Release gate: rerun the document/semantic tests and full suite after approval, fix any failures, run encrypted real-model smoke, then rebuild and inspect the installer. Current installer predates semantic work; model distribution/setup for installed copies still needs completion. Do not claim the new index is fully validated or the roadmap is complete.

Remaining roadmap work includes advanced voice/identity, all-skill process broker/isolation, call and CPU-thermal detection, live Google consent, and clean-machine/hardware verification. Semantic UI and native inference are implemented, but encrypted lifecycle integration is awaiting verification. Necessary personal-AI acceptance criteria: explicit data scope, editable/deletable memory, visible source/coverage, no silent network use, recovery/export, interruption handling, and honest setup/readiness. Existing implementations should be checked and extended instead of duplicated.


## Resumed verification, 2026-10-31
SQLCipher imports again without any security-setting changes by this agent. All 17 selected integration tests pass; full regression: 627 passed in 63.93s, 13 memory checks, frontend build/Electron syntax and 18 JavaScript checks pass (includes added model-packaging assertion). Real native-model + encrypted lifecycle smoke passes, including ranking, deletion and refusal while locked. Added upstream MIT license and explicit small-model resource to packaging. Packaged-runtime smoke also passes using the actual bundled Python, backend and model, including SQLCipher indexing/deletion/lock. No database, log, key or .env files were found in packaged backend resources. Installer build completed with exit 0: dist/SENTINEL Setup 1.0.0.exe, 1,515,298,770 bytes. Clean-machine installation remains unverified. This completes the semantic-retrieval increment, not all roadmap phases. Earlier blocked reports are historical.
