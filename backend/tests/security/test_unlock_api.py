"""
Unlock API (Phase 1, steps 1.3/1.4): status, setup, unlock, lock, rate limit, recovery,
fresh PIN for high-risk approvals, HTTP 423 and a "locked" chat message while locked.
"""
import pytest
from fastapi.testclient import TestClient

from app.core import vault as vmod
from app.core.vault import Vault

TOKEN = "unlock-api-test-token"
H = {"x-sentinel-session": TOKEN}
PIN, PIN2 = "blue-482915", "river-771133"


@pytest.fixture()
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(vmod, "KDF_PARAMS", {"iterations": 1, "lanes": 1, "memory_cost": 8192})
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", TOKEN)
    import app.main as main
    calls = {"open": [], "close": 0}

    def opener(key, first_setup, **options):
        calls["open"].append(first_setup)
        return {"migrated": False}

    def closer():
        calls["close"] += 1

    v = Vault(keystore_path=tmp_path / "keystore.json", db_opener=opener, db_closer=closer)
    monkeypatch.setattr(main, "vault", v)
    return TestClient(main.app), v, calls


def _setup(c, pin=PIN):
    r = c.post("/api/unlock/setup", json={"pin": pin}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_status_needs_the_session_token(api):
    c, *_ = api
    assert c.get("/api/unlock/status").status_code == 422
    st = c.get("/api/unlock/status", headers=H).json()
    assert st["state"] == "setup_required" and st["min_pin_length"] == vmod.MIN_PIN_LENGTH


def test_setup_lock_unlock_cycle(api):
    c, _, calls = api
    out = _setup(c)
    assert len(out["recovery_key"]) == 39 and calls["open"] == [True]
    assert c.post("/api/lock", headers=H).json()["state"] == "locked"
    assert calls["close"] == 1
    assert c.post("/api/unlock", json={"pin": "000000"}, headers=H).status_code == 401
    assert c.post("/api/unlock", json={"pin": PIN}, headers=H).json()["state"] == "unlocked"


def test_weak_pin_and_second_setup(api):
    c, *_ = api
    assert c.post("/api/unlock/setup", json={"pin": "123"}, headers=H).status_code == 400
    _setup(c)
    assert c.post("/api/unlock/setup", json={"pin": PIN}, headers=H).status_code == 409


def test_rate_limit_gives_429_with_retry_after(api):
    c, *_ = api
    _setup(c)
    c.post("/api/lock", headers=H)
    for _ in range(vmod.FREE_ATTEMPTS):
        assert c.post("/api/unlock", json={"pin": "000000"}, headers=H).status_code == 401
    r = c.post("/api/unlock", json={"pin": PIN}, headers=H)
    assert r.status_code == 429 and r.json()["detail"]["retry_after"] > 0


def test_recover_endpoint(api):
    c, *_ = api
    rk = _setup(c)["recovery_key"]
    c.post("/api/lock", headers=H)
    assert c.post("/api/unlock/recover", json={"recovery_key": rk, "new_pin": PIN2}, headers=H).status_code == 200
    c.post("/api/lock", headers=H)
    assert c.post("/api/unlock", json={"pin": PIN2}, headers=H).status_code == 200


def _register(name, tier):
    from app.core.tool_registry import RiskTier, ToolDefinition, ToolSchema, tool_registry
    tool_registry.register(ToolDefinition(tool_schema=ToolSchema(
        name=name, description="t", risk_tier=RiskTier(tier), parameters={}), executor=lambda: "done"))


def test_high_risk_approval_needs_a_fresh_pin(api, monkeypatch):
    c, v, _ = api
    _setup(c)
    v._last_pin_at -= vmod.FRESH_PIN_S + 5                         # the PIN is no longer fresh
    import app.core.secure_runner as sr
    monkeypatch.setattr(sr.secure_runner, "execute", lambda **kw: {"status": "success", "data": "done"})
    from app.core.tool_registry import tool_registry
    _register("_t_write", 3)
    try:
        body = {"token": "t", "tool_name": "_t_write", "args": {}, "session_id": "s"}
        r = c.post("/api/tools/confirm", json=body, headers=H)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "pin_required"
        assert c.post("/api/tools/confirm", json={**body, "pin": "000000"}, headers=H).status_code == 401
        assert c.post("/api/tools/confirm", json={**body, "pin": PIN}, headers=H).json()["status"] == "success"
        assert c.post("/api/tools/confirm", json=body, headers=H).status_code == 200    # fresh for a while
    finally:
        tool_registry.tools.pop("_t_write", None)


def test_lower_risk_approval_needs_no_pin(api, monkeypatch):
    c, v, _ = api
    _setup(c)
    v._last_pin_at -= vmod.FRESH_PIN_S + 5
    import app.core.secure_runner as sr
    monkeypatch.setattr(sr.secure_runner, "execute", lambda **kw: {"status": "success", "data": "done"})
    from app.core.tool_registry import tool_registry
    _register("_t_read", 2)
    try:
        body = {"token": "t", "tool_name": "_t_read", "args": {}, "session_id": "s"}
        assert c.post("/api/tools/confirm", json=body, headers=H).status_code == 200
    finally:
        tool_registry.tools.pop("_t_read", None)


def test_locked_database_gives_423(api, locked_db):
    c, *_ = api
    assert c.get("/settings", headers=H).status_code == 423


def test_chat_window_is_told_sentinel_is_locked(api, locked_db):
    c, *_ = api
    with c.websocket_connect("/ws/chat", subprotocols=["sentinel.v1", TOKEN]) as ws:
        assert ws.receive_json()["type"] == "locked"


def test_approvals_are_refused_while_locked(api):
    c, v, _ = api
    _setup(c)
    c.post("/api/lock", headers=H)
    body = {"token": "t", "tool_name": "get_system_telemetry", "args": {}, "session_id": "s"}
    assert c.post("/api/tools/confirm", json=body, headers=H).status_code == 423


def test_auto_lock_change_needs_a_fresh_pin(api):
    c, v, _ = api
    _setup(c)
    v._last_pin_at -= vmod.FRESH_PIN_S + 5
    r = c.post("/api/unlock/auto-lock", json={"minutes": 0}, headers=H)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "pin_required"
    assert c.post("/api/unlock/auto-lock", json={"minutes": 0, "pin": PIN}, headers=H).json() == {"auto_lock_minutes": 0}


def test_new_recovery_key_endpoint(api):
    c, v, _ = api
    old = _setup(c)["recovery_key"]
    v._last_pin_at -= vmod.FRESH_PIN_S + 5
    assert c.post("/api/unlock/new-recovery-key", json={}, headers=H).status_code == 403
    new = c.post("/api/unlock/new-recovery-key", json={"pin": PIN}, headers=H).json()["recovery_key"]
    assert new != old and len(new) == 39


def test_status_lists_old_plaintext_files(api):
    c, *_ = api
    st = c.get("/api/unlock/status", headers=H).json()
    assert isinstance(st["old_unencrypted_files"], list) and st["old_unencrypted_db"] == bool(st["old_unencrypted_files"])
