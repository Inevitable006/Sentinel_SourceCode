"""F01/F18/F08: the workspace router is registered and its journeys work end to end."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

TOKEN = "workspace-test-token"
H = {"X-Sentinel-Session": TOKEN}


@pytest.fixture
def web(monkeypatch):
    from app.main import app
    from app import workspace_routes as ws
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", TOKEN)
    monkeypatch.setattr(ws.vault, "is_unlocked", lambda: True)
    monkeypatch.setattr(ws.vault, "pin_fresh", lambda: True)
    from app.core import secure_runner  # noqa: F401  registers the core tools, as the running app does
    from app.core.skill_router import skill_router
    if "system_ops" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()
    return TestClient(app)


def test_routes_are_registered():
    from app.main import app
    paths = {route.path for route in app.routes}
    for p in ("/api/workspace/items/{kind}", "/api/workspace/items/{item_id}/update",
              "/api/workspace/plans/{item_id}/run", "/api/workspace/memory", "/api/workspace/history",
              "/api/workspace/skills", "/api/workspace/privacy", "/api/workspace/emergency-stop"):
        assert p in paths, p


def test_unauthorized_and_locked_requests_are_rejected(web, monkeypatch):
    from app import workspace_routes as ws
    assert web.get("/api/workspace/items/task").status_code == 422
    assert web.get("/api/workspace/items/task", headers={"X-Sentinel-Session": "wrong"}).status_code == 401
    monkeypatch.setattr(ws.vault, "is_unlocked", lambda: False)
    assert web.get("/api/workspace/items/task", headers=H).status_code == 423


def test_create_edit_list_delete_draft(web):
    created = web.post("/api/workspace/items/email_draft", headers=H, json={"title": "Hello", "content": "v1"}).json()
    edited = web.post(f"/api/workspace/items/{created['id']}/update", headers=H,
                      json={"title": "Hello again", "content": "v2"})
    assert edited.status_code == 200 and edited.json()["content"] == "v2"
    listed = web.get("/api/workspace/items/email_draft", headers=H).json()
    assert any(i["id"] == created["id"] and i["title"] == "Hello again" for i in listed)
    assert web.post(f"/api/workspace/items/{created['id']}/delete", headers=H, json={}).json() == {"deleted": True}
    assert web.post(f"/api/workspace/items/{created['id']}/update", headers=H, json={"title": "x"}).status_code == 404


def test_invalid_input_fails(web):
    assert web.post("/api/workspace/items/task", headers=H, json={"title": ""}).status_code == 422
    assert web.post("/api/workspace/items/task", headers=H, json={"title": "t", "due_at": "2026-01-01T10:00"}).status_code == 422
    assert web.post("/api/workspace/items/plan", headers=H, json={"title": "empty plan"}).status_code == 400


def _plan(web, steps):
    return web.post("/api/workspace/items/plan", headers=H, json={"title": "p", "steps": steps}).json()


def _run_step(web, plan):
    prep = web.post(f"/api/workspace/plans/{plan['id']}/prepare", headers=H).json()
    return web.post(f"/api/workspace/plans/{plan['id']}/run", headers=H,
                    json={"token": prep["token"], "revision": prep["revision"]})


def test_failed_step_does_not_advance_the_plan(web, tmp_path):
    plan = _plan(web, [{"tool": "run_system_op", "args": {"operation": "list_directory", "target": str(tmp_path)}}])
    result = _run_step(web, plan).json()
    assert result["status"] == "failed"
    assert result["payload"]["next"] == 0


def test_successful_plan_completes(web):
    plan = _plan(web, [{"tool": "run_system_op", "args": {"operation": "echo_text", "target": "hi"}}])
    result = _run_step(web, plan).json()
    assert result["status"] == "done" and result["payload"]["next"] == 1
    # Started plans cannot be silently rewritten.
    assert web.post(f"/api/workspace/items/{plan['id']}/update", headers=H,
                    json={"title": "x", "steps": [{"tool": "run_system_op", "args": {"operation": "echo_text", "target": "y"}}]}).status_code == 409


def test_lock_during_a_step_leaves_a_reviewable_state(web, monkeypatch):
    from app import workspace_routes as ws
    plan = _plan(web, [{"tool": "run_system_op", "args": {"operation": "echo_text", "target": "hi"}}])
    prep = web.post(f"/api/workspace/plans/{plan['id']}/prepare", headers=H).json()
    calls = []
    def lock_after_running(*args, **kwargs):
        calls.append(args)
        monkeypatch.setattr(ws.vault, "is_unlocked", lambda: False)   # owner locks mid-action
        return {"status": "success", "data": "hi"}
    from app.core import secure_runner as sr
    monkeypatch.setattr(sr.secure_runner, "execute", lock_after_running)
    assert web.post(f"/api/workspace/plans/{plan['id']}/run", headers=H,
                    json={"token": prep["token"], "revision": prep["revision"]}).status_code == 423
    monkeypatch.setattr(ws.vault, "is_unlocked", lambda: True)
    item = next(i for i in web.get("/api/workspace/items/plan", headers=H).json() if i["id"] == plan["id"])
    assert item["status"] == "interrupted" and len(calls) == 1
    # Not runnable until the owner reviews and resumes it; then it is ready again.
    assert web.post(f"/api/workspace/plans/{plan['id']}/prepare", headers=H).status_code == 409
    assert web.post(f"/api/workspace/items/{plan['id']}/state", headers=H, json={"status": "open"}).json()["status"] == "ready"


def test_stale_running_rows_are_recovered_after_restart():
    from app import workspace_routes as ws
    from app.db.database import SessionLocal
    from app.db.models import WorkItem
    with SessionLocal() as db:
        db.add(WorkItem(id="stale-plan", kind="plan", title="t", content="", status="running",
                        payload=json.dumps({"steps": [], "next": 0, "results": []})))
        db.commit()
    assert ws.recover_interrupted() >= 1
    with SessionLocal() as db:
        assert db.get(WorkItem, "stale-plan").status == "interrupted"


def test_reminders_become_due_without_listing():
    from app import workspace_routes as ws
    from app.db.database import SessionLocal
    from app.db.models import WorkItem
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with SessionLocal() as db:
        db.add(WorkItem(id="due-task", kind="task", title="t", content="", status="open", due_at=past, payload="{}"))
        db.commit()
    ws.due_reminders()   # what the background loop calls
    with SessionLocal() as db:
        assert db.get(WorkItem, "due-task").status == "due"


def test_disabled_skill_is_blocked_through_every_alias(web):
    from app.core.secure_runner import secure_runner
    assert web.post("/api/workspace/skills/system_ops", headers=H, json={"enabled": False}).json() == {"enabled": False}
    try:
        for tool, args in (("run_system_op", {"operation": "echo_text", "target": "x"}),
                           ("skill_system_op", {"operation": "echo_text", "target": "x"})):
            result = secure_runner.execute(tool, args, "skill-off", force_confirmation=True)
            assert result["status"] == "error" and "turned off" in result["message"], tool
    finally:
        web.post("/api/workspace/skills/system_ops", headers=H, json={"enabled": True})
    result = secure_runner.execute("run_system_op", {"operation": "echo_text", "target": "x"}, "skill-on", force_confirmation=True)
    assert result["status"] == "needs_confirmation"
