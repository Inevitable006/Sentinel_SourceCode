"""Daily briefing: reminders, plans, portfolio change, PC health, backup age."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import briefing
from app.db.database import SessionLocal
from app.db.models import PortfolioHistory, WorkItem


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    with SessionLocal() as db:
        db.query(WorkItem).delete(); db.query(PortfolioHistory).delete(); db.commit()
    from app.core import backup
    monkeypatch.setattr(backup, "BACKUP_DIR", tmp_path / "backups")


def add_item(id, kind, title, status="open", due=None):
    with SessionLocal() as db:
        db.add(WorkItem(id=id, kind=kind, title=title, content="", status=status, due_at=due,
                        payload=json.dumps({"steps": [], "next": 0, "results": []})))
        db.commit()


def test_empty_briefing_says_so_plainly():
    b = briefing.build_briefing(datetime(2026, 10, 10, 8, 0).astimezone())
    assert b["greeting"] == "Good morning"
    assert b["reminders"]["due_today"] == [] and b["plans"] == []
    assert b["portfolio"]["available"] is False
    assert b["backup"]["due"] is True
    assert "No reminders are due today." in b["spoken"] and "time to make a backup" in b["spoken"]


def test_reminders_plans_and_portfolio_change():
    now = datetime.now().astimezone()
    utc = now.astimezone(timezone.utc)
    add_item("t1", "task", "Pay electricity bill", "due", (utc - timedelta(hours=1)).isoformat())
    add_item("t2", "task", "Call the bank", "open", (utc + timedelta(minutes=30)).isoformat())
    add_item("t3", "task", "Next week thing", "open", (utc + timedelta(days=7)).isoformat())
    add_item("p1", "plan", "Clean downloads", "interrupted")
    from app.portfolio_routes import record_history
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    record_history({"count": 1, "value": 10000, "invested": 9000}, day=yesterday)
    record_history({"count": 1, "value": 10250, "invested": 9000}, day=now.date().isoformat())
    b = briefing.build_briefing(now)
    titles = [r["title"] for r in b["reminders"]["due_today"]]
    assert titles == ["Pay electricity bill", "Call the bank"]          # next week's task is not today
    assert b["reminders"]["due_today"][0]["overdue"] is True
    assert b["plans"][0]["status"] == "interrupted"
    assert b["portfolio"]["change"] == 250 and b["portfolio"]["change_pct"] == 2.5
    assert "up 250 rupees" in b["spoken"] and "1 plan needs" in b["spoken"]


def test_one_history_row_per_day():
    from app.portfolio_routes import record_history
    record_history({"count": 1, "value": 1, "invested": 1}, day="2026-10-01")
    record_history({"count": 1, "value": 2, "invested": 1}, day="2026-10-01")
    with SessionLocal() as db:
        assert db.query(PortfolioHistory).count() == 1
        assert db.get(PortfolioHistory, "2026-10-01").value == 2


def test_route_requires_unlock(monkeypatch):
    from app.main import app
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "brief-token")
    H = {"X-Sentinel-Session": "brief-token"}
    monkeypatch.setattr(briefing.vault, "is_unlocked", lambda: False)
    assert TestClient(app).get("/api/briefing", headers=H).status_code == 423
    monkeypatch.setattr(briefing.vault, "is_unlocked", lambda: True)
    assert TestClient(app).get("/api/briefing", headers=H).json()["greeting"]


def test_today_ends_at_local_midnight():
    # 22:00 local: a reminder at 23:30 local is today; one at 00:30 local tomorrow is not.
    now = datetime.now().astimezone().replace(hour=22, minute=0, second=0, microsecond=0)
    add_item("late", "task", "Late tonight", "open", now.replace(hour=23, minute=30).astimezone(timezone.utc).isoformat())
    add_item("tmrw", "task", "Tomorrow early", "open", (now + timedelta(hours=2, minutes=30)).astimezone(timezone.utc).isoformat())
    titles = [r["title"] for r in briefing.build_briefing(now)["reminders"]["due_today"]]
    assert titles == ["Late tonight"]
