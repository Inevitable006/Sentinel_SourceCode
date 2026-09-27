"""
UI-session-token enforcement on REST endpoints.

Uses TestClient without entering the app lifespan, so no DB setup,
governor loop or skill loading runs.
"""
import pytest
from fastapi.testclient import TestClient

TOKEN = "unit-test-session-token"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", TOKEN)
    from app.main import app
    return TestClient(app)


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/governor/status", None),
    ("post", "/api/governor/mode", {"paused": True}),
    ("get", "/api/models", None),
    ("post", "/api/models/unload", None),
    ("get", "/settings", None),
])
def test_protected_endpoints_reject_missing_token(client, method, path, body):
    r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert r.status_code in (401, 422)


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/governor/status", None),
    ("post", "/api/governor/mode", {"paused": True}),
])
def test_protected_endpoints_reject_wrong_token(client, method, path, body):
    headers = {"X-Sentinel-Session": "wrong-token"}
    if body is not None:
        r = getattr(client, method)(path, json=body, headers=headers)
    else:
        r = getattr(client, method)(path, headers=headers)
    assert r.status_code == 401


def test_governor_status_accepts_valid_token(client):
    r = client.get("/api/governor/status", headers={"X-Sentinel-Session": TOKEN})
    assert r.status_code == 200


def test_health_stays_public(client):
    assert client.get("/health").status_code == 200


def test_websocket_rejects_bad_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat?token=wrong") as ws:
            ws.receive_json()


def test_token_compare_helper():
    from app.main import _token_matches
    assert _token_matches("abc", "abc")
    assert not _token_matches("abc", "abd")
    assert not _token_matches(None, "abc")
    assert not _token_matches("abc", None)
    assert not _token_matches("", "")
