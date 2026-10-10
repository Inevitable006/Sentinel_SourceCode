"""'What did Sentinel do?': audit events become plain, correctly paired entries."""
import time

from app.core.activity import build_activity

T = time.time()


import pytest


@pytest.fixture(autouse=True, scope="module")
def skills_registered():
    from app.core import secure_runner  # noqa: F401
    from app.core.skill_router import skill_router
    if "file_manager" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()


def ev(kind, offset, **details):
    return {"timestamp": T + offset, "event_type": kind, "details": details}


def test_approved_run_is_one_entry():
    items = build_activity(now=T + 100, entries=[
        ev("confirmation_requested", 0, tool_name="skill_write_file", session_id="chat1"),
        ev("execution_started", 5, tool_name="skill_write_file", session_id="chat1"),
        ev("execution_success", 6, tool_name="skill_write_file", session_id="chat1", duration=0.42),
    ])["items"]
    assert len(items) == 1
    assert items[0]["approval"] == "approved by you" and items[0]["status"] == "done"
    assert items[0]["outcome"] == "done in 0.4 s" and items[0]["from"] == "chat"
    assert items[0]["action"].startswith("Create or overwrite a text file")


def test_declined_failed_blocked_and_read_only():
    result = build_activity(now=T + 100, entries=[
        ev("confirmation_requested", 0, tool_name="search_web", session_id="c"),               # never approved
        ev("confirmation_requested", 10, tool_name="run_system_op", session_id="c"),
        ev("execution_failed", 12, tool_name="run_system_op", session_id="c", error="Tool execution failed"),
        ev("execution_denied_skill_disabled", 20, tool_name="skill_execute_python_code", session_id="c", skill="python_coding"),
        ev("policy_evaluation", 30, tool_name="delete_everything", session_id="c", decision="deny", reason="Tier 4 is blocked"),
        ev("execution_success", 40, tool_name="get_service_health", session_id="c", duration=0.01),   # tier 1, no approval
        ev("system_watch_offline", 50, reason="critical alert"),
    ])
    by_status = {i["action"]: (i["status"], i["approval"]) for i in result["items"]}
    assert result["counts"] == {"done": 2, "failed": 1, "blocked": 2, "not_approved": 1}
    assert any(s == ("not_approved", "asked") for s in by_status.values())
    assert by_status["Switched Sentinel to Offline mode"][0] == "done"
    assert any(i["approval"] == "not needed (read-only)" for i in result["items"])
    assert result["items"][0]["time"] >= result["items"][-1]["time"]        # newest first


def test_old_entries_are_outside_the_window():
    items = build_activity(days=1, now=T, entries=[ev("execution_success", -3 * 86400, tool_name="x", session_id="c")])["items"]
    assert items == []


def test_plan_origin_is_named(monkeypatch):
    import app.core.activity as act
    monkeypatch.setattr(act, "_origins", lambda: {"plan-42": "Tidy downloads"})
    items = build_activity(now=T + 10, entries=[ev("execution_success", 0, tool_name="x", session_id="plan-42")])["items"]
    assert items[0]["from"] == "plan “Tidy downloads”"
