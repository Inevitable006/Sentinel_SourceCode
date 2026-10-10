"""Per-skill hourly limits: refused before approval, counted when actions start, owner-adjustable."""
import pytest
from fastapi.testclient import TestClient

from app.core.rate_limits import SkillRate, skill_rate
from app.core.secure_runner import secure_runner


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    from app.core.skill_router import skill_router
    if "system_ops" not in skill_router._skills:
        from app.core.skill_loader import register_all_skills
        register_all_skills()
    skill_rate._runs.clear()
    import app.workspace_routes as ws
    monkeypatch.setitem(ws.DEFAULT_LIMITS, "system_ops", 2)
    yield
    skill_rate._runs.clear()
    from app.db.database import SessionLocal
    from app.db.models import WorkItem
    with SessionLocal() as db:
        db.query(WorkItem).filter(WorkItem.id == "skill:system_ops").delete(); db.commit()


def run_echo():
    args = {"operation": "echo_text", "target": "hi"}
    first = secure_runner.execute("run_system_op", args, "limits", force_confirmation=True)
    if first["status"] != "needs_confirmation":
        return first
    return secure_runner.execute("run_system_op", args, "limits", token=first["token"])


def test_limit_refuses_before_asking_for_approval():
    assert run_echo()["status"] == "success"
    assert run_echo()["status"] == "success"
    third = run_echo()
    assert third["status"] == "error" and "limit of 2 actions per hour" in third["message"]


def test_pending_approvals_cannot_exceed_the_limit():
    args = {"operation": "echo_text", "target": "hi"}
    tokens = [secure_runner.execute("run_system_op", args, "limits", force_confirmation=True)["token"] for _ in range(3)]
    results = [secure_runner.execute("run_system_op", args, "limits", token=t)["status"] for t in tokens]
    assert results == ["success", "success", "error"]


def test_window_slides():
    rate = SkillRate()
    for t in (0, 10):
        rate.record("s", now=1000 + t)
    assert rate.check("s", 2, now=1500) == 3600 - 500 + 1
    assert rate.check("s", 2, now=1000 + 3600) is None      # first run left the window
    assert rate.check("s", 0, now=1500) is None              # 0 = unlimited


def test_owner_can_change_the_limit(monkeypatch):
    from app.main import app
    import app.workspace_routes as ws
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "lim-token")
    monkeypatch.setattr(ws.vault, "is_unlocked", lambda: True)
    monkeypatch.setattr(ws.vault, "pin_fresh", lambda: True)
    web, H = TestClient(app), {"X-Sentinel-Session": "lim-token"}
    assert web.post("/api/workspace/skills/system_ops/limit", headers=H, json={"limit_per_hour": 5}).status_code == 200
    assert ws.skill_limit("system_ops") == 5
    skills = {s["name"]: s for s in web.get("/api/workspace/skills", headers=H).json()}
    assert skills["system_ops"]["limit_per_hour"] == 5 and "used_last_hour" in skills["system_ops"]
    assert web.post("/api/workspace/skills/system_ops/limit", headers=H, json={"limit_per_hour": -1}).status_code == 422
    monkeypatch.setattr(ws.vault, "pin_fresh", lambda: False)
    assert web.post("/api/workspace/skills/system_ops/limit", headers=H, json={"limit_per_hour": 9}).status_code == 403


def test_activity_shows_limit_blocks():
    import time
    from app.core.activity import build_activity
    now = time.time()
    items = build_activity(now=now + 5, entries=[
        {"timestamp": now, "event_type": "execution_denied_rate_limit",
         "details": {"tool_name": "run_system_op", "session_id": "c", "skill": "system_ops"}}])["items"]
    assert items[0]["status"] == "blocked" and "hourly limit" in items[0]["outcome"]
