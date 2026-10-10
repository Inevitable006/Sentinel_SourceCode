"""F21: a reconnecting window can continue its conversation instead of starting over."""
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.core.memory_service import memory_service


def _connect(client):
    return client.websocket_connect("/ws/chat", subprotocols=["sentinel.v1", "resume-token"])


def _until(ws, kind):
    for _ in range(10):
        msg = ws.receive_json()
        if msg["type"] == kind:
            return msg
    raise AssertionError(f"no {kind} message")


def test_resume_existing_thread(monkeypatch):
    from app.main import app
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "resume-token")
    with SessionLocal() as db:
        earlier = memory_service.create_thread(db, title="Earlier")
        memory_service.add_message(db, earlier, "user", "first question")
        memory_service.add_message(db, earlier, "system", "internal note")
        memory_service.add_message(db, earlier, "assistant", "first answer")
    with _connect(TestClient(app)) as ws:
        fresh = _until(ws, "thread")["thread_id"]
        assert fresh != earlier
        ws.send_json({"type": "resume", "thread_id": earlier})
        resumed = _until(ws, "resumed")
        assert resumed["thread_id"] == earlier
        assert resumed["messages"] == [{"role": "user", "content": "first question"},
                                       {"role": "assistant", "content": "first answer"}]


def test_unknown_thread_is_refused(monkeypatch):
    from app.main import app
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "resume-token")
    with _connect(TestClient(app)) as ws:
        _until(ws, "thread")
        ws.send_json({"type": "resume", "thread_id": "not-a-thread"})
        assert "no longer exists" in _until(ws, "error")["message"]
