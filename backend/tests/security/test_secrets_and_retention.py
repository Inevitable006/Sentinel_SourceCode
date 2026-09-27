"""
Step 1.5 (secrets vault) and step 1.6 (real deletion + retention), on the encrypted test database.
"""
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import redaction, retention, secrets_store
from app.core import vault as vmod
from app.core.vault import Vault
from app.db import database as dbm

TOKEN = "retention-test-token"
H = {"x-sentinel-session": TOKEN}
PIN = "blue-482915"


# ── secrets vault ───────────────────────────────────────────────

def test_secret_round_trip_and_listing_hides_values():
    secrets_store.set_secret("calendar.api_key", "cal-key-0123456789")
    try:
        assert secrets_store.get_secret("calendar.api_key") == "cal-key-0123456789"
        listed = secrets_store.list_secrets()
        assert any(s["name"] == "calendar.api_key" for s in listed)
        assert "cal-key-0123456789" not in str(listed)
        assert "cal-key-0123456789" not in redaction.redact("log line with cal-key-0123456789")
    finally:
        assert secrets_store.delete_secret("calendar.api_key") is True
    assert secrets_store.get_secret("calendar.api_key") is None


def test_secret_value_is_not_on_disk():
    secrets_store.set_secret("disk.check", "zz-unique-secret-5550123")
    try:
        assert b"zz-unique-secret-5550123" not in dbm.ENCRYPTED_DB_PATH.read_bytes()
    finally:
        secrets_store.delete_secret("disk.check")


@pytest.mark.parametrize("name", ["", "has space", "x" * 65, "semi;colon"])
def test_bad_secret_names(name):
    with pytest.raises(secrets_store.SecretError):
        secrets_store.set_secret(name, "value-123456")


def test_secrets_are_unavailable_while_locked(locked_db):
    with pytest.raises(dbm.DatabaseLocked):
        secrets_store.list_secrets()


# ── deletion ────────────────────────────────────────────────────

def test_forget_all_memories_clears_rows_and_search_index():
    from app.core.memory_service import memory_service
    db = dbm.SessionLocal()
    try:
        assert memory_service.remember(db, "I keep my bicycle in the blue shed")
    finally:
        db.close()
    assert retention.forget_all_memories() >= 1
    with dbm.get_engine().connect() as c:
        assert c.execute(text("SELECT count(*) FROM memory_items")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM fts_memory_items")).scalar() == 0


def test_delete_all_chats():
    from app.core.memory_service import memory_service
    db = dbm.SessionLocal()
    try:
        tid = memory_service.create_thread(db, title="to delete")
        memory_service.add_message(db, tid, "user", "hello")
    finally:
        db.close()
    assert retention.delete_all_chats() >= 1
    with dbm.get_engine().connect() as c:
        assert c.execute(text("SELECT count(*) FROM threads")).scalar() == 0
        assert c.execute(text("SELECT count(*) FROM messages")).scalar() == 0


# ── retention ───────────────────────────────────────────────────

def _db_time(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def test_retention_defaults_and_validation():
    assert retention.get_settings() == {"retention_chat_days": 180, "retention_research_days": 90}
    with pytest.raises(ValueError):
        retention.set_settings(-1, 90)


def test_retention_removes_old_chats_research_and_expired_memories():
    now = time.time()
    old, new = now - 400 * 86400, now - 86400
    old_tid, new_tid, mem_id = f"old-{uuid.uuid4()}", f"new-{uuid.uuid4()}", f"exp-{uuid.uuid4()}"
    with dbm.get_engine().begin() as c:
        c.execute(text("INSERT INTO threads (id, title, created_at) VALUES (:i, 'old', :t)"), {"i": old_tid, "t": _db_time(old)})
        c.execute(text("INSERT INTO messages (thread_id, role, content) VALUES (:i, 'user', 'old message')"), {"i": old_tid})
        c.execute(text("INSERT INTO threads (id, title, created_at) VALUES (:i, 'new', :t)"), {"i": new_tid, "t": _db_time(new)})
        c.execute(text("INSERT INTO research_history (query, url, title, timestamp) VALUES ('old q', 'u', 't', :t)"), {"t": old})
        c.execute(text("INSERT INTO research_history (query, url, title, timestamp) VALUES ('new q', 'u', 't', :t)"), {"t": new})
        c.execute(text("INSERT INTO memory_items (id, content, confidence, importance, expires_at) "
                       "VALUES (:i, 'temporary note', 100, 3, :e)"), {"i": mem_id, "e": _db_time(now - 60)})
    removed = retention.apply_retention(now)
    assert removed["chats"] >= 1 and removed["research"] >= 1 and removed["expired_memories"] >= 1
    with dbm.get_engine().connect() as c:
        ids = {r[0] for r in c.execute(text("SELECT id FROM threads"))}
        assert old_tid not in ids and new_tid in ids
        assert c.execute(text("SELECT count(*) FROM messages WHERE thread_id = :i"), {"i": old_tid}).scalar() == 0
        queries = {r[0] for r in c.execute(text("SELECT query FROM research_history"))}
        assert "old q" not in queries and "new q" in queries
        assert c.execute(text("SELECT count(*) FROM memory_items WHERE id = :i"), {"i": mem_id}).scalar() == 0


def test_zero_means_keep_forever():
    retention.set_settings(0, 0)
    try:
        tid = f"ancient-{uuid.uuid4()}"
        with dbm.get_engine().begin() as c:
            c.execute(text("INSERT INTO threads (id, title, created_at) VALUES (:i, 'x', :t)"),
                      {"i": tid, "t": _db_time(time.time() - 3000 * 86400)})
        retention.apply_retention()
        with dbm.get_engine().connect() as c:
            assert c.execute(text("SELECT count(*) FROM threads WHERE id = :i"), {"i": tid}).scalar() == 1
    finally:
        retention.set_settings(180, 90)


# ── API: every destructive or sensitive change needs a fresh PIN ─

@pytest.fixture()
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(vmod, "KDF_PARAMS", {"iterations": 1, "lanes": 1, "memory_cost": 8192})
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", TOKEN)
    import app.main as main
    v = Vault(keystore_path=tmp_path / "keystore.json", db_opener=lambda k, f, **o: {}, db_closer=lambda: None)
    monkeypatch.setattr(main, "vault", v)
    c = TestClient(main.app)
    assert c.post("/api/unlock/setup", json={"pin": PIN}, headers=H).status_code == 200
    v._last_pin_at -= vmod.FRESH_PIN_S + 5          # PIN no longer fresh
    return c


@pytest.mark.parametrize("path,body", [
    ("/api/secrets", {"name": "k1", "value": "value-123456"}),
    ("/api/secrets/k1/delete", {}),
    ("/api/memory/forget-all", {}),
    ("/api/chats/delete-all", {}),
    ("/api/retention", {"chat_days": 30, "research_days": 30}),
])
def test_sensitive_endpoints_need_a_fresh_pin(api, path, body):
    r = api.post(path, json=body, headers=H)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "pin_required"


def test_secret_api_saves_and_lists_names_only(api):
    assert api.post("/api/secrets", json={"name": "api.k", "value": "value-7777777", "pin": PIN}, headers=H).status_code == 200
    listed = api.get("/api/secrets", headers=H).json()["secrets"]
    assert any(s["name"] == "api.k" for s in listed) and "value-7777777" not in str(listed)
    assert api.post("/api/secrets/api.k/delete", json={}, headers=H).json() == {"deleted": True}   # PIN fresh now


def test_retention_api_round_trip(api):
    r = api.post("/api/retention", json={"chat_days": 365, "research_days": 30, "pin": PIN}, headers=H)
    assert r.status_code == 200 and r.json()["settings"] == {"retention_chat_days": 365, "retention_research_days": 30}
    assert api.get("/api/retention", headers=H).json()["retention_chat_days"] == 365
    api.post("/api/retention", json={"chat_days": 180, "research_days": 90}, headers=H)
