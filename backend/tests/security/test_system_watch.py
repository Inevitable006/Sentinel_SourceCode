"""T-06 System Watch: fixtures only, nothing on the real PC is changed."""
import copy

import pytest
from fastapi.testclient import TestClient

from app.core import system_watch as sw
from app.core.system_watch import analyze, SystemWatch

NORMAL = {
    "startup": {r"HKCU:\...\Run\OneDrive": r"C:\Program Files\OneDrive\OneDrive.exe"},
    "tasks": {r"\GoogleUpdateTask": r"C:\Program Files\Google\Update\GoogleUpdate.exe /c"},
    "services": {"Spooler": r"C:\Windows\System32\spoolsv.exe"},
    "admins": {r"PC\owner": "User"},
    "firewall": {"Domain": True, "Private": True, "Public": True},
    "defender": {"present": True, "antivirus": True, "realtime": True, "signature_age_days": 0},
    "threats": [], "suspicious_processes": [], "self_integrity": [],
}


def baseline_of(snapshot):
    return {c: dict(snapshot[c]) for c in sw.BASELINE_CATEGORIES}


def changed(**updates):
    s = copy.deepcopy(NORMAL)
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update(v)
        else:
            s[k] = v
    return s


def ids(alerts):
    return {a["id"]: a["severity"] for a in alerts}


def test_normal_pc_has_no_alerts():
    assert analyze(NORMAL, baseline_of(NORMAL), set()) == []


@pytest.mark.parametrize("snapshot, expected_id, severity", [
    (changed(startup={r"HKCU:\...\Run\Updater": r"C:\Users\o\Downloads\upd.exe"}), r"startup:HKCU:\...\Run\Updater", "critical"),
    (changed(startup={r"HKCU:\...\Run\Zoom": r"C:\Program Files\Zoom\zoom.exe"}), r"startup:HKCU:\...\Run\Zoom", "warning"),
    (changed(tasks={r"\Sync": r"C:\Users\Public\x.ps1"}), r"tasks:\Sync", "critical"),
    (changed(services={"EvilSvc": r"C:\Windows\Temp\svc.exe"}), "services:EvilSvc", "critical"),
    (changed(admins={r"PC\helpdesk": "User"}), r"admins:PC\helpdesk", "critical"),
    (changed(firewall={"Public": False}), "firewall:Public", "critical"),
    (changed(defender={"present": True, "antivirus": True, "realtime": False, "signature_age_days": 0}), "defender:realtime_off", "critical"),
    (changed(defender={"present": True, "antivirus": True, "realtime": True, "signature_age_days": 30}), "defender:signatures_old", "warning"),
    (changed(threats=[{"id": "7", "resources": "file:_C:\\x.exe", "when": "t", "action_success": False}]), "threat:7", "critical"),
    (changed(suspicious_processes=[{"exe": r"C:\Users\o\Downloads\miner.exe", "network": True}]), r"process:c:\users\o\downloads\miner.exe", "warning"),
    (changed(self_integrity=[{"key": "audit_log", "detail": "x"}]), "sentinel:audit_log", "critical"),
])
def test_each_kind_of_problem_raises_an_alert_with_steps(snapshot, expected_id, severity):
    alerts = analyze(snapshot, baseline_of(NORMAL), set())
    assert ids(alerts).get(expected_id) == severity, ids(alerts)
    assert all(a["steps"] for a in alerts)


def test_changed_startup_command_is_reported():
    s = changed(startup={r"HKCU:\...\Run\OneDrive": r"C:\Users\o\AppData\Local\Temp\od.exe"})
    alert = next(a for a in analyze(s, baseline_of(NORMAL), set()) if a["id"].endswith("#changed"))
    assert "Was:" in alert["detail"] and "Now:" in alert["detail"]


@pytest.fixture
def watch(monkeypatch):
    from app.db.database import SessionLocal
    from app.db.models import WatchAlert, WatchBaseline
    with SessionLocal() as db:
        db.query(WatchAlert).delete(); db.query(WatchBaseline).delete(); db.commit()
    from app.core.egress import egress_guard
    offline = []
    monkeypatch.setattr(egress_guard, "set_offline", lambda value: offline.append(value))
    monkeypatch.setattr(egress_guard, "status", lambda: {"offline": bool(offline)})
    return SystemWatch(), offline


def test_first_run_becomes_baseline_then_new_item_alerts_and_accept_stops_it(watch):
    w, offline = watch
    assert w.run_check(NORMAL)["first_run"] is True
    assert w.status()["alerts"] == []
    new = changed(startup={r"HKCU:\...\Run\Zoom": r"C:\Program Files\Zoom\zoom.exe"})
    assert w.run_check(new)["alerts"] == 1
    alert = w.status()["alerts"][0]
    assert w.accept(alert["id"])
    assert w.run_check(new)["alerts"] == 0              # now part of normal
    assert offline == []                                 # a warning never changes anything


def test_critical_alert_switches_to_offline_mode_only(watch):
    w, offline = watch
    w.run_check(NORMAL)
    result = w.run_check(changed(firewall={"Public": False}))
    assert result["critical"] == 1 and offline == [True]


def test_fixed_problem_is_marked_resolved(watch):
    w, _ = watch
    w.run_check(NORMAL)
    w.run_check(changed(firewall={"Public": False}))
    assert len(w.status()["alerts"]) == 1
    w.run_check(NORMAL)
    assert w.status()["alerts"] == []


def test_collect_script_is_read_only():
    script = sw.COLLECT_SCRIPT
    for verb in ("Set-", "Remove-", "Stop-", "New-", "Start-", "Disable-", "Enable-", "Invoke-Expression", "iex "):
        assert verb not in script, verb


def test_routes_need_token_unlock_and_pin(monkeypatch):
    from app.main import app
    from app import watch_routes
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "watch-token")
    H = {"X-Sentinel-Session": "watch-token"}
    web = TestClient(app)
    assert web.get("/api/watch/status").status_code == 422
    monkeypatch.setattr(watch_routes.vault, "is_unlocked", lambda: False)
    assert web.get("/api/watch/status", headers=H).status_code == 423
    monkeypatch.setattr(watch_routes.vault, "is_unlocked", lambda: True)
    assert web.get("/api/watch/status", headers=H).status_code == 200
    monkeypatch.setattr(watch_routes.vault, "pin_fresh", lambda: False)
    assert web.post("/api/watch/defender-scan", headers=H, json={}).status_code == 403
    assert web.post("/api/watch/alerts/x/accept", headers=H, json={}).status_code == 403
