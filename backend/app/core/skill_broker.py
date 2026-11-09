"""
Parent-owned broker authority for contained skill execution.

Provides an in-memory authority primitive and deny-by-default request dispatch
for approved skill effects. Binds immutable validated arguments, request identity,
generation, deadline, and a single-operation budget.

This is an authority primitive for T-17; it does not introduce worker transport,
runtime routing changes, or public API endpoints.
"""

from __future__ import annotations

import copy
import json
import math
import threading
import time
from typing import Any, Callable, Dict, Mapping, Optional, Tuple


# Proposed default frame and budget limits per SKILL_BROKER_DESIGN.md
MAX_REQUEST_FRAME_BYTES = 8192      # 8 KiB maximum worker request frame
MAX_RESULT_FRAME_BYTES = 16384     # 16 KiB maximum text result frame
DEFAULT_DEADLINE_SECONDS = 15.0     # 15-second wall clock deadline
DEFAULT_OPERATION_BUDGET = 1        # One read operation per approved execution


class BrokerError(Exception):
    """Base class for skill broker errors."""
    pass


class BrokerRevokedError(BrokerError):
    """Authority was revoked before or during execution."""
    pass


class BrokerExpiredError(BrokerError):
    """Request deadline passed before or during execution."""
    pass


class BrokerProtocolError(BrokerError):
    """Worker sent a malformed, invalid, or unexpected request frame."""
    pass


class BrokerBudgetExceededError(BrokerError):
    """Worker exceeded its approved operation budget."""
    pass


class BrokerSecurityError(BrokerError):
    """Worker attempted unauthorized operation, argument alteration, or field injection."""
    pass


# Type alias for trusted parent read adapter: (target, frozen_args) -> str
ReadAdapter = Callable[[str, Mapping[str, Any]], str]


class BrokerResult:
    """Bounded, safe result DTO returned by broker authority dispatch."""

    __slots__ = ("ok", "data", "error", "truncated")

    def __init__(
        self,
        ok: bool,
        data: Optional[str] = None,
        error: Optional[str] = None,
        truncated: bool = False,
    ) -> None:
        self.ok = ok
        self.data = data
        self.error = error
        self.truncated = truncated

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "truncated": self.truncated,
        }

    def __repr__(self) -> str:
        return (
            f"BrokerResult(ok={self.ok!r}, "
            f"data_len={len(self.data) if self.data else 0}, "
            f"error={self.error!r}, truncated={self.truncated!r})"
        )


class ParentBrokerAuthority:
    """
    Parent-owned authority token and dispatcher for a single skill invocation.

    Invariants:
    1. Immutable arguments: Approved arguments are deep-copied and frozen on creation.
       A worker can never supply or alter targets, paths, or parameters.
    2. Trusted adapter: Target and adapter are provided by trusted parent code.
    3. Strict framing: Requests must be <= 8 KiB, strictly valid JSON, with exact
       expected keys ('op', 'seq'). Any extra fields are rejected.
    4. Monotonic sequencing: Request sequence must strictly equal expected sequence.
    5. One-operation budget: Operation count is enforced; concurrent overlapping
       calls are rejected.
    6. Non-blocking revocation: The lock is NOT held during the adapter call.
       Revocation/cancellation remains immediately responsive.
    7. Post-call verification: Revocation, deadline expiry, and generation changes
       during the adapter call suppress the result and release resources.
    8. Safe output: Output is bounded to 16 KiB; raw adapter exceptions are
       sanitized and never leak private internal details.
    """

    ALLOWED_OPERATIONS = frozenset({"read"})
    ALLOWED_FRAME_KEYS = frozenset({"op", "seq"})

    def __init__(
        self,
        tool_name: str,
        approved_args: Mapping[str, Any],
        target: str,
        request_id: str,
        generation: int,
        read_adapter: ReadAdapter,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
        budget: int = DEFAULT_OPERATION_BUDGET,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError("tool_name must be a non-empty string")
        if not target or not isinstance(target, str):
            raise ValueError("target must be a non-empty string")
        if not request_id or not isinstance(request_id, str):
            raise ValueError("request_id must be a non-empty string")
        if not callable(read_adapter):
            raise ValueError("read_adapter must be callable")
        if type(budget) is not int or budget < 1:
            raise ValueError("budget must be at least 1")
        if type(generation) is not int or generation < 0:
            raise ValueError("generation must be a nonnegative integer")
        if type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive and finite")

        self._tool_name = tool_name
        # Deep-copy approved arguments to create an immutable snapshot
        self._approved_args: Mapping[str, Any] = copy.deepcopy(dict(approved_args))
        self._target = target
        self._request_id = request_id
        self._generation = int(generation)
        self._generation_invalidated = False
        self._read_adapter = read_adapter
        self._budget = int(budget)
        self._clock = clock

        # Set deadline based on supplied clock
        self._start_time = self._clock()
        self._deadline = self._start_time + float(deadline_seconds)
        if not math.isfinite(self._start_time) or not math.isfinite(self._deadline):
            raise ValueError("clock and deadline must be finite")

        # Internal synchronization and state
        self._lock = threading.Lock()
        self._revoked = False
        self._revocation_reason: Optional[str] = None
        self._seq = 0
        self._ops_consumed = 0
        self._in_flight = False

    @property
    def tool_name(self) -> str:
        return self._tool_name

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def is_revoked(self) -> bool:
        with self._lock:
            return self._revoked

    @property
    def approved_args(self) -> Mapping[str, Any]:
        # Return a copy to preserve immutability
        return copy.deepcopy(dict(self._approved_args))

    @property
    def target(self) -> str:
        return self._target

    def update_generation(self, new_generation: int) -> None:
        """Update the lock/session generation. In-flight calls with older gen will be rejected."""
        if type(new_generation) is not int or new_generation < 0:
            raise ValueError("generation must be a nonnegative integer")
        with self._lock:
            self._generation_invalidated |= new_generation != self._generation
            self._generation = new_generation

    def revoke(self, reason: str = "revoked by parent") -> None:
        """
        Immediately revoke authority. Non-blocking and thread-safe.
        Any in-flight or subsequent requests will be refused.
        """
        with self._lock:
            self._revoked = True
            self._revocation_reason = reason

    def dispatch_raw(self, raw_frame: bytes | str) -> BrokerResult:
        """
        Parse and dispatch a raw worker frame (bytes or JSON string).
        Enforces frame length limits before parsing.
        """
        if isinstance(raw_frame, bytes):
            if len(raw_frame) > MAX_REQUEST_FRAME_BYTES:
                return BrokerResult(
                    ok=False,
                    error=f"Request frame exceeded maximum size of {MAX_REQUEST_FRAME_BYTES} bytes",
                )
            try:
                text = raw_frame.decode("utf-8")
            except UnicodeDecodeError:
                return BrokerResult(ok=False, error="Request frame contains invalid UTF-8 bytes")
        elif isinstance(raw_frame, str):
            # Check UTF-8 byte length
            if len(raw_frame) > MAX_REQUEST_FRAME_BYTES:
                return BrokerResult(ok=False, error="Request frame exceeded maximum size")
            try:
                encoded = raw_frame.encode("utf-8")
            except UnicodeEncodeError:
                return BrokerResult(ok=False, error="Request frame contains invalid UTF-8 text")
            if len(encoded) > MAX_REQUEST_FRAME_BYTES:
                return BrokerResult(
                    ok=False,
                    error=f"Request frame exceeded maximum size of {MAX_REQUEST_FRAME_BYTES} bytes",
                )
            text = raw_frame
        else:
            return BrokerResult(ok=False, error="Request frame must be bytes or str")

        def unique_fields(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate field')
                result[key] = value
            return result
        def invalid_constant(value):
            raise ValueError('Nonfinite JSON')
        try:
            parsed = json.loads(text, object_pairs_hook=unique_fields, parse_constant=invalid_constant)
        except (ValueError, RecursionError):
            return BrokerResult(ok=False, error="Request frame is not valid JSON")

        if not isinstance(parsed, dict):
            return BrokerResult(ok=False, error="Request frame JSON must be an object")

        return self.dispatch(parsed)

    def dispatch(self, frame: Dict[str, Any]) -> BrokerResult:
        """
        Dispatch a parsed request frame through authority controls.

        Step 1: Check revocation, deadline, sequence, budget, concurrency, and field whitelist.
        Step 2: Release lock and execute trusted adapter.
        Step 3: Re-acquire lock, re-verify revocation/deadline/generation.
        Step 4: Bound output and return safe result.
        """
        if not isinstance(frame, dict):
            return BrokerResult(ok=False, error="Request must be a dictionary")

        # Pre-check lock and validations
        with self._lock:
            if self._revoked:
                return BrokerResult(
                    ok=False,
                    error=f"Authority revoked: {self._revocation_reason or 'revoked'}",
                )

            now = self._clock()
            if not math.isfinite(now) or now >= self._deadline:
                return BrokerResult(ok=False, error="Request deadline expired")
            if self._generation_invalidated:
                return BrokerResult(ok=False, error="Generation changed; authority invalidated")

            # Validate frame keys: strictly {"op", "seq"} - no extra fields permitted!
            frame_keys = set(frame.keys())
            if frame_keys != self.ALLOWED_FRAME_KEYS:
                extra = frame_keys - self.ALLOWED_FRAME_KEYS
                missing = self.ALLOWED_FRAME_KEYS - frame_keys
                if extra:
                    return BrokerResult(
                        ok=False,
                        error="Unauthorized extra fields in request frame",
                    )
                if missing:
                    return BrokerResult(
                        ok=False,
                        error=f"Missing required fields in request frame: {sorted(list(missing))}",
                    )

            op = frame.get("op")
            if not isinstance(op, str) or op not in self.ALLOWED_OPERATIONS:
                return BrokerResult(
                    ok=False,
                    error="Unsupported operation (expected read)",
                )

            # Monotonic sequence check
            seq = frame.get("seq")
            if not isinstance(seq, int) or isinstance(seq, bool):
                return BrokerResult(ok=False, error="Sequence number must be an integer")

            expected_seq = self._seq + 1
            if seq != expected_seq:
                return BrokerResult(
                    ok=False,
                    error=f"Invalid sequence number {seq} (expected {expected_seq})",
                )

            # Operation budget check
            if self._ops_consumed >= self._budget:
                return BrokerResult(
                    ok=False,
                    error=f"Operation budget exceeded ({self._ops_consumed}/{self._budget} consumed)",
                )

            # Concurrency check: one outstanding message allowed
            if self._in_flight:
                return BrokerResult(ok=False, error="Concurrent request already in flight")

            # Enter execution state
            self._in_flight = True
            self._seq = seq
            self._ops_consumed += 1
            entry_generation = self._generation

        # --- EXECUTION PHASE (Lock is NOT held during adapter call) ---
        raw_output: Optional[str] = None
        adapter_error: Optional[str] = None

        try:
            # Trusted parent passes parent-approved target and immutable args
            raw_output = self._read_adapter(self._target, self.approved_args)
        except Exception as exc:
            # Suppress raw traceback or sensitive detail; provide sanitized description
            adapter_error = f"Adapter execution failed: {type(exc).__name__}"

        # --- POST-EXECUTION PHASE (Re-acquire lock to verify state) ---
        with self._lock:
            self._in_flight = False

            # Check if revoked while adapter was running
            if self._revoked:
                return BrokerResult(
                    ok=False,
                    error=f"Authority revoked during execution: {self._revocation_reason or 'revoked'}",
                )

            # Check if deadline expired while adapter was running
            now = self._clock()
            if not math.isfinite(now) or now >= self._deadline:
                return BrokerResult(ok=False, error="Request deadline expired during execution")

            # Check if generation changed while adapter was running
            if self._generation_invalidated or self._generation != entry_generation:
                return BrokerResult(
                    ok=False,
                    error="Generation changed during execution (session state invalidated)",
                )

        if adapter_error is not None:
            return BrokerResult(ok=False, error=adapter_error)

        if raw_output is None:
            return BrokerResult(ok=True, data="", truncated=False)

        if not isinstance(raw_output, str):
            return BrokerResult(ok=False, error="Adapter returned invalid output type")

        # Enforce output bounds (16 KiB maximum text)
        try:
            utf8_bytes = raw_output[:MAX_RESULT_FRAME_BYTES + 1].encode("utf-8")
        except UnicodeEncodeError:
            return BrokerResult(ok=False, error="Adapter returned invalid UTF-8 text")
        if len(utf8_bytes) > MAX_RESULT_FRAME_BYTES:
            # Truncate at UTF-8 byte boundary
            truncated_bytes = utf8_bytes[:MAX_RESULT_FRAME_BYTES]
            truncated_text = truncated_bytes.decode("utf-8", errors="ignore")
            return BrokerResult(ok=True, data=truncated_text, truncated=True)

        return BrokerResult(ok=True, data=raw_output, truncated=False)

