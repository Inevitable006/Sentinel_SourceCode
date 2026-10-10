"""F03: a tool that fails must come back from SecureRunner as status=error.

These run the real skill wrappers and the real SafeProcess runner (no run_command mocks),
so they catch the false "Action completed" the audit found.
"""
import pytest

from app.core.secure_runner import secure_runner
from app.core.skill_router import skill_router
from app.core.tool_registry import ToolFailure, failed, is_failure


@pytest.fixture(scope="module", autouse=True)
def skills_registered():
    if "python_coding" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()


def run_confirmed(tool, args, session="f03"):
    """Goes through the normal confirmation token flow, then executes."""
    first = secure_runner.execute(tool, args, session, force_confirmation=True)
    assert first["status"] == "needs_confirmation", first
    return secure_runner.execute(tool, args, session, token=first["token"])


def test_failure_marker_keeps_text():
    f = failed("Error: nope")
    assert isinstance(f, ToolFailure) and is_failure(f)
    assert f == "Error: nope" and "nope" in f
    assert not is_failure("Error: plain strings are not failures")


def test_real_python_failure_is_reported_as_error():
    # A script that fails in the real contained runner must not look like success.
    result = run_confirmed("skill_execute_python_code", {"code": "raise SystemExit(3)"})
    assert result["status"] == "error", result
    assert "data" not in result
    blocked = run_confirmed("skill_execute_python_code", {"code": "import socket"})
    assert blocked["status"] == "error", blocked


def test_real_python_success_is_success():
    result = run_confirmed("skill_execute_python_code", {"code": "print(6 * 7)"})
    assert result["status"] == "success" and "42" in result["data"], result


def test_missing_document_is_reported_as_error(tmp_path):
    from app.core.paths import SENTINEL_DATA_DIR
    missing = SENTINEL_DATA_DIR / "does-not-exist.txt"
    result = run_confirmed("skill_read_document", {"file_path": str(missing)})
    assert result["status"] == "error", result


def test_missing_blender_is_reported_as_error(monkeypatch):
    import skills.app_control as app_control
    monkeypatch.setattr(app_control, "_find_blender_executable", lambda: None)
    result = run_confirmed("skill_run_blender_script", {"script_code": "pass"})
    assert result["status"] == "error", result


def test_network_failure_is_reported_as_error():
    # Tests have no internet (conftest), so the market-data request fails.
    result = run_confirmed("skill_get_market_data", {"symbol": "TEST"})
    assert result["status"] == "error", result


def test_blocked_directory_listing_is_reported_as_error(tmp_path):
    result = run_confirmed("run_system_op", {"operation": "list_directory", "target": str(tmp_path)})
    assert result["status"] == "error", result


def test_successful_tool_is_still_success():
    result = run_confirmed("run_system_op", {"operation": "echo_text", "target": "hello"})
    assert result == {"status": "success", "data": "hello"}
