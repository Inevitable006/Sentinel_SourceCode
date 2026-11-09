"""
Security and authority tests for ParentBrokerAuthority (T-17).

Verifies parent-owned broker authority:
- Immutable approved arguments snapshot
- Deny-by-default on extra fields, unknown operations, invalid sequence
- Zero adapter calls on denial, expiration, or pre-revocation
- Budget enforcement (one operation)
- Non-blocking revocation and revocation during blocked reads
- Generation change during execution
- Deadline expiration before and during execution
- Concurrency protection (adapter invoked at most once)
- Output size truncation (16 KiB cap)
- Safe exception suppression (no leak of private strings)
- Raw frame byte length enforcement (8 KiB cap)
"""

import threading
import time
import pytest

from app.core.skill_broker import (
    MAX_REQUEST_FRAME_BYTES,
    MAX_RESULT_FRAME_BYTES,
    BrokerResult,
    ParentBrokerAuthority,
)


class FakeClock:
    """Controllable monotonic clock for deterministic deadline tests."""

    def __init__(self, start_time: float = 1000.0) -> None:
        self._time = float(start_time)

    def __call__(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += float(seconds)


def test_happy_path_read_execution():
    """Valid read request succeeds and invokes adapter with parent-approved target and args."""
    clock = FakeClock(100.0)
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append((target, dict(args)))
        return "synthetic file contents"

    approved_args = {"mode": "summary", "max_length": 500}
    authority = ParentBrokerAuthority(
        tool_name="document_reader",
        approved_args=approved_args,
        target="docs/sample.txt",
        request_id="req-001",
        generation=1,
        read_adapter=synthetic_adapter,
        deadline_seconds=10.0,
        budget=1,
        clock=clock,
    )

    result = authority.dispatch({"op": "read", "seq": 1})

    assert result.ok is True
    assert result.data == "synthetic file contents"
    assert result.error is None
    assert result.truncated is False

    assert len(adapter_calls) == 1
    assert adapter_calls[0][0] == "docs/sample.txt"
    assert adapter_calls[0][1] == {"mode": "summary", "max_length": 500}


def test_immutable_arguments_snapshot():
    """Mutating the original arguments dict does not mutate the frozen snapshot held by authority."""
    clock = FakeClock()
    received_args = []

    def synthetic_adapter(target: str, args: dict) -> str:
        received_args.append(dict(args))
        return "ok"

    original_args = {"path": "safe.txt", "nested": {"key": "val1"}}
    authority = ParentBrokerAuthority(
        tool_name="doc_tool",
        approved_args=original_args,
        target="safe.txt",
        request_id="req-002",
        generation=1,
        read_adapter=synthetic_adapter,
        clock=clock,
    )

    # Malicious caller or caller code mutates original dictionary before dispatch
    original_args["path"] = "attack.txt"
    original_args["nested"]["key"] = "tampered"
    original_args["injected"] = "malicious"

    result = authority.dispatch({"op": "read", "seq": 1})
    assert result.ok is True

    # Adapter must have received the original frozen snapshot
    assert len(received_args) == 1
    assert received_args[0]["path"] == "safe.txt"
    assert received_args[0]["nested"]["key"] == "val1"
    assert "injected" not in received_args[0]


def test_extra_fields_in_frame_denied_zero_adapter_calls():
    """Worker attempting to pass arbitrary path, target, or credentials is denied before adapter."""
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={"file": "test.txt"},
        target="test.txt",
        request_id="req-003",
        generation=1,
        read_adapter=synthetic_adapter,
    )

    # Worker passes target in frame
    res1 = authority.dispatch({"op": "read", "seq": 1, "target": "/etc/shadow"})
    assert res1.ok is False
    assert "Unauthorized extra fields" in res1.error
    assert len(adapter_calls) == 0

    # Worker passes custom path in frame
    res2 = authority.dispatch({"op": "read", "seq": 1, "path": "../secret.key"})
    assert res2.ok is False
    assert "Unauthorized extra fields" in res2.error
    assert len(adapter_calls) == 0


def test_unsupported_operation_denied_zero_adapter_calls():
    """Worker requesting mutation or unknown operation is denied before adapter."""
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-004",
        generation=1,
        read_adapter=synthetic_adapter,
    )

    result = authority.dispatch({"op": "write", "seq": 1})
    assert result.ok is False
    assert "Unsupported operation" in result.error
    assert len(adapter_calls) == 0


def test_sequence_monotonicity_enforced():
    """Out-of-order, skipped, zero, or non-integer sequence numbers are denied."""
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-005",
        generation=1,
        read_adapter=synthetic_adapter,
        budget=5,
    )

    # Starting at seq 2 instead of 1
    res1 = authority.dispatch({"op": "read", "seq": 2})
    assert res1.ok is False
    assert "Invalid sequence number" in res1.error
    assert len(adapter_calls) == 0

    # String sequence number
    res2 = authority.dispatch({"op": "read", "seq": "1"})
    assert res2.ok is False
    assert "Sequence number must be an integer" in res2.error
    assert len(adapter_calls) == 0

    # Boolean sequence number (bool is subclass of int in Python)
    res3 = authority.dispatch({"op": "read", "seq": True})
    assert res3.ok is False
    assert "Sequence number must be an integer" in res3.error
    assert len(adapter_calls) == 0

    # Correct sequence 1 succeeds
    res4 = authority.dispatch({"op": "read", "seq": 1})
    assert res4.ok is True
    assert len(adapter_calls) == 1

    # Repeating sequence 1 (replay attempt)
    res5 = authority.dispatch({"op": "read", "seq": 1})
    assert res5.ok is False
    assert "Invalid sequence number" in res5.error
    assert len(adapter_calls) == 1


def test_operation_budget_enforced():
    """Default budget of 1 allows exactly 1 operation; subsequent requests rejected."""
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-006",
        generation=1,
        read_adapter=synthetic_adapter,
        budget=1,
    )

    res1 = authority.dispatch({"op": "read", "seq": 1})
    assert res1.ok is True
    assert len(adapter_calls) == 1

    res2 = authority.dispatch({"op": "read", "seq": 2})
    assert res2.ok is False
    assert "Operation budget exceeded" in res2.error
    assert len(adapter_calls) == 1


def test_revocation_before_call_causes_zero_adapter_calls():
    """Revoked authority refuses dispatch immediately."""
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-007",
        generation=1,
        read_adapter=synthetic_adapter,
    )

    authority.revoke("Sentinel locked")
    assert authority.is_revoked is True

    result = authority.dispatch({"op": "read", "seq": 1})
    assert result.ok is False
    assert "Authority revoked: Sentinel locked" in result.error
    assert len(adapter_calls) == 0


def test_deadline_expired_before_call():
    """Expired deadline refuses dispatch immediately."""
    clock = FakeClock(100.0)
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-008",
        generation=1,
        read_adapter=synthetic_adapter,
        deadline_seconds=5.0,
        clock=clock,
    )

    # Advance clock past 5.0 seconds
    clock.advance(5.1)

    result = authority.dispatch({"op": "read", "seq": 1})
    assert result.ok is False
    assert "deadline expired" in result.error.lower()
    assert len(adapter_calls) == 0


def test_revocation_during_blocked_read_suppresses_result():
    """If authority is revoked while adapter is executing, the result is discarded."""
    adapter_started = threading.Event()
    continue_adapter = threading.Event()
    adapter_called = []

    def blocking_adapter(target: str, args: dict) -> str:
        adapter_called.append(True)
        adapter_started.set()
        continue_adapter.wait(timeout=5.0)
        return "sensitive output"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-009",
        generation=1,
        read_adapter=blocking_adapter,
    )

    dispatch_result = []

    def runner():
        res = authority.dispatch({"op": "read", "seq": 1})
        dispatch_result.append(res)

    t = threading.Thread(target=runner)
    t.start()

    # Wait until adapter is executing
    assert adapter_started.wait(timeout=2.0)

    # Revoke authority while adapter is in-flight!
    # Lock must NOT be blocked by the adapter call
    authority.revoke("user emergency stop")

    # Let adapter complete
    continue_adapter.set()
    t.join(timeout=2.0)

    assert len(dispatch_result) == 1
    res = dispatch_result[0]
    assert res.ok is False
    assert "revoked during execution" in res.error.lower()
    assert res.data is None  # Sensitive data must NOT be released!


def test_generation_change_during_blocked_read_suppresses_result():
    """If lock generation changes while adapter is executing, result is suppressed."""
    adapter_started = threading.Event()
    continue_adapter = threading.Event()

    def blocking_adapter(target: str, args: dict) -> str:
        adapter_started.set()
        continue_adapter.wait(timeout=5.0)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-010",
        generation=1,
        read_adapter=blocking_adapter,
    )

    dispatch_result = []

    def runner():
        res = authority.dispatch({"op": "read", "seq": 1})
        dispatch_result.append(res)

    t = threading.Thread(target=runner)
    t.start()

    assert adapter_started.wait(timeout=2.0)

    # Generation increments (e.g. session re-locked/unlocked)
    authority.update_generation(2)

    continue_adapter.set()
    t.join(timeout=2.0)

    assert len(dispatch_result) == 1
    res = dispatch_result[0]
    assert res.ok is False
    assert "generation changed" in res.error.lower()
    assert res.data is None


def test_deadline_expiry_during_blocked_read_suppresses_result():
    """If deadline passes while adapter is executing, result is suppressed."""
    clock = FakeClock(100.0)
    adapter_started = threading.Event()
    continue_adapter = threading.Event()

    def blocking_adapter(target: str, args: dict) -> str:
        adapter_started.set()
        continue_adapter.wait(timeout=5.0)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-011",
        generation=1,
        read_adapter=blocking_adapter,
        deadline_seconds=5.0,
        clock=clock,
    )

    dispatch_result = []

    def runner():
        res = authority.dispatch({"op": "read", "seq": 1})
        dispatch_result.append(res)

    t = threading.Thread(target=runner)
    t.start()

    assert adapter_started.wait(timeout=2.0)

    # Clock advances past deadline while in-flight
    clock.advance(10.0)

    continue_adapter.set()
    t.join(timeout=2.0)

    assert len(dispatch_result) == 1
    res = dispatch_result[0]
    assert res.ok is False
    assert "deadline expired during execution" in res.error.lower()
    assert res.data is None


def test_concurrent_requests_execute_adapter_at_most_once():
    """Concurrent overlapping requests are rejected (at most one in-flight)."""
    adapter_started = threading.Event()
    continue_adapter = threading.Event()
    adapter_calls = []

    def blocking_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        adapter_started.set()
        continue_adapter.wait(timeout=5.0)
        return "first result"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-012",
        generation=1,
        read_adapter=blocking_adapter,
        budget=2,
    )

    results = []

    def worker_1():
        results.append(("w1", authority.dispatch({"op": "read", "seq": 1})))

    def worker_2():
        results.append(("w2", authority.dispatch({"op": "read", "seq": 2})))

    t1 = threading.Thread(target=worker_1)
    t1.start()

    assert adapter_started.wait(timeout=2.0)

    # Second worker tries while first is in-flight
    t2 = threading.Thread(target=worker_2)
    t2.start()
    t2.join(timeout=2.0)

    continue_adapter.set()
    t1.join(timeout=2.0)

    assert len(results) == 2
    by_worker = {w: res for w, res in results}

    # Worker 1 succeeded
    assert by_worker["w1"].ok is True
    assert by_worker["w1"].data == "first result"

    # Worker 2 was rejected due to concurrent in-flight
    assert by_worker["w2"].ok is False
    assert "concurrent request already in flight" in by_worker["w2"].error.lower()

    # Adapter was called exactly once
    assert len(adapter_calls) == 1


def test_output_size_truncation_to_16kib():
    """Adapter output exceeding 16 KiB is truncated and marked truncated=True."""
    oversized_data = "A" * (MAX_RESULT_FRAME_BYTES + 5000)

    def large_adapter(target: str, args: dict) -> str:
        return oversized_data

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="large.txt",
        request_id="req-013",
        generation=1,
        read_adapter=large_adapter,
    )

    result = authority.dispatch({"op": "read", "seq": 1})
    assert result.ok is True
    assert len(result.data.encode("utf-8")) == MAX_RESULT_FRAME_BYTES
    assert result.truncated is True


def test_adapter_exceptions_suppressed_no_private_leaks():
    """Raw exception strings (paths, tokens, details) are suppressed and sanitized."""
    def failing_adapter(target: str, args: dict) -> str:
        raise PermissionError("Private vault file C:\\Users\\owner\\private.db is locked")

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="private.db",
        request_id="req-014",
        generation=1,
        read_adapter=failing_adapter,
    )

    result = authority.dispatch({"op": "read", "seq": 1})
    assert result.ok is False
    # Error should contain safe exception type name, but NOT the sensitive message
    assert "PermissionError" in result.error
    assert "private.db" not in result.error
    assert "owner" not in result.error


def test_raw_frame_size_limit_and_malformed_json():
    """Raw frames > 8 KiB or malformed JSON rejected before execution."""
    adapter_calls = []

    def synthetic_adapter(target: str, args: dict) -> str:
        adapter_calls.append(target)
        return "data"

    authority = ParentBrokerAuthority(
        tool_name="reader",
        approved_args={},
        target="file.txt",
        request_id="req-015",
        generation=1,
        read_adapter=synthetic_adapter,
    )

    # Frame exceeding 8 KiB
    huge_bytes = b"{" + b"a" * (MAX_REQUEST_FRAME_BYTES + 10) + b"}"
    res1 = authority.dispatch_raw(huge_bytes)
    assert res1.ok is False
    assert "exceeded maximum size" in res1.error
    assert len(adapter_calls) == 0

    # Invalid UTF-8
    bad_utf8 = b"\xff\xfe\x00\x00"
    res2 = authority.dispatch_raw(bad_utf8)
    assert res2.ok is False
    assert "invalid utf-8" in res2.error.lower()
    assert len(adapter_calls) == 0

    # Malformed JSON
    res3 = authority.dispatch_raw(b"{invalid json")
    assert res3.ok is False
    assert "valid json" in res3.error.lower()
    assert len(adapter_calls) == 0

    # Valid JSON string dispatch
    res4 = authority.dispatch_raw('{"op": "read", "seq": 1}')
    assert res4.ok is True
    assert res4.data == "data"
    assert len(adapter_calls) == 1

