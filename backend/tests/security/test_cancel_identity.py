"""F09/F12: cancellation reaches the exact processes of one request; output budgets are enforced while reading."""
import os
import sys
import threading
import time

import psutil
import pytest

from app.core.request_context import cancel_request_work
from app.core.safe_process import safe_process, MAX_CAPTURE_BYTES
from app.core.secure_runner import secure_runner
from app.core.tool_registry import tool_registry, ToolDefinition, ToolSchema, RiskTier

PING = r"c:\windows\system32\ping.exe"
pytestmark = pytest.mark.skipif(os.name != "nt" or not os.path.exists(PING), reason="Windows ping needed")


def slow_wrapper(**kwargs):
    # Like skill wrappers: only **kwargs, no session/request parameters.
    ok, out, err = safe_process.run_command([PING, "-n", "30", "127.0.0.1"], timeout_seconds=60)
    return out if ok else f"stopped: {err}"


tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(name="test_slow_action", description="slow", risk_tier=RiskTier.TIER_3, parameters={}),
    executor=slow_wrapper))


def _wait_for_job(job, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        pids = list(safe_process.active_processes.get(job, ()))
        if pids:
            return pids
        time.sleep(0.05)
    raise AssertionError(f"no process started for {job}")


def test_approved_action_is_cancelled_by_request_id_only():
    first = secure_runner.execute("test_slow_action", {}, "chat-thread", force_confirmation=True)
    results = {}
    runner = threading.Thread(target=lambda: results.update(r=secure_runner.execute(
        "test_slow_action", {}, "chat-thread", request_id="req-A", token=first["token"])))
    other = threading.Thread(target=lambda: results.update(b=safe_process.run_command(
        [PING, "-n", "30", "127.0.0.1"], timeout_seconds=60, job_id="req-B")))
    runner.start(); other.start()
    a_pids = _wait_for_job("req-A")
    b_pids = _wait_for_job("req-B")
    started = time.time()
    cancel_request_work("req-A")
    runner.join(10)
    assert not runner.is_alive() and time.time() - started < 10
    assert all(not psutil.pid_exists(p) or psutil.Process(p).status() == psutil.STATUS_ZOMBIE for p in a_pids)
    assert all(psutil.pid_exists(p) for p in b_pids), "an unrelated job was stopped"
    cancel_request_work("req-B")
    other.join(10)
    assert "req-A" not in safe_process.active_processes and "req-B" not in safe_process.active_processes


def test_output_budget_stops_a_flooding_process():
    # The real Python interpreter is allowed only for this call (as the sandboxed runner does).
    exe = os.path.abspath(sys.executable).lower()
    code = "import sys\nwhile True: sys.stdout.write('x' * 65536)"
    started = time.time()
    ok, out, err = safe_process.run_command([exe, "-c", code], timeout_seconds=30, job_id="flood",
                                            extra_allowed=frozenset([exe]))
    assert not ok and "budget" in err
    assert time.time() - started < 25
    assert "flood" not in safe_process.active_processes


def test_kept_output_is_capped():
    exe = os.path.abspath(sys.executable).lower()
    ok, out, err = safe_process.run_command([exe, "-c", f"print('y' * {MAX_CAPTURE_BYTES // 4})"],
                                            extra_allowed=frozenset([exe]))
    assert ok and len(out) < 11 * 1024 and "TRUNCATED" in out
