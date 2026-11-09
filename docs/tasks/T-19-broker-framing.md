# T-19: Bounded broker message framing

Owner authorized continued autonomous work, 2026-11-02. Branch phase1/security. Scope: new backend/app/core/broker_protocol.py, backend/tests/security/test_broker_protocol.py, this card and coordination records. No auth, process-launch, frontend, dependency or runtime routing changes.

Implement one complete request/response exchange around ParentBrokerAuthority using a four-byte unsigned big-endian payload length. Limit request JSON to 8 KiB and the entire encoded response JSON to 16 KiB (including keys/escaping), excluding the four-byte prefix. Reject missing/trailing bytes and oversized advertised frames before JSON parsing. Unknown protocol requests, malformed frames and failed authority dispatch revoke the authority. Serialize only bounded text and fixed safe error messages; never raw exceptions, targets or credentials. Completion does not grant new operations. Tests use synthetic adapters only.

This is framing/dispatch, not a live subprocess transport. Future pipe reader must reject advertised size before reading the body and provide deadline/cancellation termination; this module does not claim to interrupt blocking I/O. Existing production tools unchanged.

## Report
Completed framing/dispatch, 2026-11-02. Added broker_protocol.py and 16 tests covering successful response/replay, invalid and oversized frames, malformed requests, safe revocation errors and ASCII/control/multibyte/escaped response bounds. A four-byte header helper validates advertised length before the future reader allocates a body. No worker process/socket or runtime route added.

Focused broker checks: 47 passed in 0.45s. Full backend regression: **712 passed in 34.72s**, tools/check.ps1 -Only pytest. Initial verification encountered a pytest-reserved parameter name and Windows environment-length errors from generated long test IDs; corrected the test harness with descriptive short IDs. Production tests were not skipped/weakened.

Still required: real deadline-aware/cancellable pipe transport, cleanup on partial messages/EOF/lock, exact process binding and approved read adapter. Do not describe this framing increment as full broker activation. Existing installer unchanged; no frontend edits.
