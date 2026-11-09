# T-17: Parent-owned broker authority

Codex handback review, 2026-11-02: ownership of broker/test/card and check.ps1 accepted back from AntiGravity. Scope extends to correcting malformed protocol handling, argument snapshot mutation, invalid deadline/budget configuration and generation invalidation, with regression tests. Broker remains unconnected to production routing. No dependency or authentication changes.

Review corrections completed: malformed/unhashable ops, invalid UTF-8, duplicate/nonfinite JSON and deeply nested frames fail safely; constructor rejects invalid deadlines and budget types; adapter receives a defensive argument copy; generation changes permanently invalidate authority; output encoding allocates only a bounded slice and rejects invalid types/text. Added test_skill_broker_edges.py (16 cases). All 31 broker tests passed; combined tools/check.ps1 -Only tests passed exit 0 on 2026-11-02. No runtime transport/activation. AntiGravity's original report below is historical; these corrections supersede its blanket completeness claims.

State: IMPLEMENTATION AND VERIFICATION COMPLETE. Branch phase1/security.

Ownership update 2026-11-01: owner asked Codex to stop. AntiGravity implemented this task during the scoped six-hour handoff; see docs/coordination/ANTIGRAVITY_SIX_HOUR_HANDOFF.md. Codex released this card and its two implementation/test paths. Runtime activation remains strictly excluded.

Read docs/coordination/SKILL_BROKER_DESIGN.md and existing SecureRunner, file_ops, egress and skill_router before coding.

Bounded scope: new backend/app/core/skill_broker.py and backend/tests/security/test_skill_broker.py plus this report. Implemented an internal parent authority object and deny-by-default dispatch for a single explicitly supplied read adapter. Freezes/copies arguments, binds request identity/generation/deadline, enforces one operation and monotonic sequence, refuses invalid frames and revokes on close. Adapter is supplied by trusted parent code; never resolves a function or path from a worker string. No public API, worker transport, runtime route, filesystem/network/database adapter or auth changes in this task. No new dependencies.

Tests: denied/expired/revoked requests cause zero adapter calls; altered targets/extra fields/invalid sequence rejected; duplicate and concurrent requests invoke the adapter at most once; returned data is bounded; exceptions do not leak raw private strings; revocation during a read suppresses its result. Used a fake clock and synthetic adapters; did not access owner data. Did not add generic extensibility beyond this scope.

Completion: focused behavioral checks, source review against design, report exact results and leave production routing unchanged. Transport/read-adapter activation remains a separate future task. Broker or all-skills isolation is NOT marked complete from this authority-only increment.

## Report

- **Implementation**: `backend/app/core/skill_broker.py`
  - Created `ParentBrokerAuthority` and `BrokerResult` DTO.
  - Binds canonical `tool_name`, immutable deep-copied `approved_args`, trusted `target`, `request_id`, `generation`, and `deadline`.
  - Frame bounds enforced: max request frame 8,192 bytes (8 KiB); max result frame 16,384 bytes (16 KiB).
  - Strict framing: requires exactly `{"op": "read", "seq": int}` with zero extra fields permitted.
  - Concurrency & locking: synchronization lock is released before invoking the trusted read adapter so parent revocation/cancellation remains non-blocking; state, generation, and deadline are re-verified upon return.
  - Safe error handling: raw adapter exceptions are caught and sanitized to exception type names, preventing leakage of private paths or credentials.
  - Monotonic sequence and single-operation budget enforced.
- **Verification**: `backend/tests/security/test_skill_broker.py`
  - 15 focused security and behavioral tests passing (0.44s):
    1. `test_happy_path_read_execution`: Valid read request succeeds with exact approved target and frozen args.
    2. `test_immutable_arguments_snapshot`: Mutating original argument dict does not affect internal frozen snapshot.
    3. `test_extra_fields_in_frame_denied_zero_adapter_calls`: Extra fields (`target`, `path`) rejected with zero adapter calls.
    4. `test_unsupported_operation_denied_zero_adapter_calls`: Write and unknown operations rejected with zero adapter calls.
    5. `test_sequence_monotonicity_enforced`: Sequence gaps, non-ints, and replays rejected.
    6. `test_operation_budget_enforced`: Default budget of 1 strictly enforced; second call rejected.
    7. `test_revocation_before_call_causes_zero_adapter_calls`: Pre-revoked authority rejects dispatch immediately.
    8. `test_deadline_expired_before_call`: Expired deadline rejects dispatch before adapter.
    9. `test_revocation_during_blocked_read_suppresses_result`: Revocation during blocking call suppresses result and releases resources.
    10. `test_generation_change_during_blocked_read_suppresses_result`: Session/lock generation change during blocking call suppresses result.
    11. `test_deadline_expiry_during_blocked_read_suppresses_result`: Clock expiry during blocking call suppresses result.
    12. `test_concurrent_requests_execute_adapter_at_most_once`: Concurrent in-flight calls rejected; adapter executed at most once.
    13. `test_output_size_truncation_to_16kib`: Output > 16 KiB truncated at 16,384 bytes with `truncated=True`.
    14. `test_adapter_exceptions_suppressed_no_private_leaks`: Sensitive paths and private strings masked on adapter failure.
    15. `test_raw_frame_size_limit_and_malformed_json`: Raw frames > 8 KiB, invalid UTF-8, and non-dict JSON rejected.
- **Runtime Isolation Status**: Authority primitive implemented only. Production skill routing and `SkillRouter` remain unchanged.
