"""Google integration uses mocked provider traffic and real isolated loopback OAuth callback."""
import asyncio
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import google_workspace as google
from app.core import secrets_store

CLIENT_ID = "test-client.apps.googleusercontent.com"
TOKEN = "google-route-test-token"
HEADERS = {"X-Sentinel-Session": TOKEN}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(google.vault, "is_unlocked", lambda: True)
    monkeypatch.setattr(google.vault, "pin_fresh", lambda: True)
    monkeypatch.setattr(google.egress_guard, "offline", False)
    google.disconnect()
    google.configure(CLIENT_ID, "test-client-secret")
    yield
    monkeypatch.setattr(google.vault, "is_unlocked", lambda: True)
    google.disconnect()


def token_data(scope=None):
    return {"access_token": "test-access-token", "refresh_token": "test-refresh-token", "expires_in": 3600,
            "token_type": "Bearer", "scope": scope if scope is not None else " ".join(google.SCOPES.values())}


def authorize():
    result = google.start()
    query = parse_qs(urlsplit(result["authorization_url"]).query)
    pending = google._pending
    assert query["code_challenge_method"] == ["S256"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(pending["verifier"].encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [challenge]
    assert query["scope"] == [" ".join(google.SCOPES.values())]
    callback = query["redirect_uri"][0] + "?" + urlencode({"state": query["state"][0], "code": "test-authorization-code"})
    return pending, callback


def test_real_callback_and_one_time_exchange(monkeypatch):
    pending, callback = authorize()
    with pytest.raises(HTTPError) as error:
        urlopen(pending["redirect_uri"] + "?state=wrong&code=fake", timeout=3)
    assert error.value.code == 400
    assert urlopen(callback, timeout=3).status == 200
    assert google.status()["callback_received"]
    assert google._accept_callback(urlsplit(callback).path + "?" + urlsplit(callback).query, pending)[0] == 409
    request = AsyncMock(return_value=token_data())
    monkeypatch.setattr(google, "_request", request)
    result = asyncio.run(google.finish())
    assert result["connected"] and result["gmail"] and result["calendar"]
    assert "test-access-token" not in json.dumps(result)
    sent = request.call_args.kwargs["data"]
    assert sent["code_verifier"] == pending["verifier"] and sent["grant_type"] == "authorization_code"
    with pytest.raises(google.GoogleError):
        asyncio.run(google.finish())
    assert request.await_count == 1


def test_bad_state_expiry_and_lock_invalidate_callback():
    pending, callback = authorize()
    assert google._accept_callback("/callback?state=%C3%A9&code=x", pending)[0] == 400
    pending["expires"] = time.monotonic() - 1
    assert google._accept_callback(callback, pending)[0] == 410
    google.cancel("lock")
    assert not google.status()["pending"]
    with pytest.raises(google.GoogleError):
        asyncio.run(google.finish())


def test_granular_scope_refused_before_network(monkeypatch):
    google._save_tokens(token_data(google.SCOPES["calendar"]), google._generation)
    request = AsyncMock()
    monkeypatch.setattr(google, "_request", request)
    with pytest.raises(google.GoogleError, match="not granted"):
        asyncio.run(google.messages())
    request.assert_not_called()


def test_refresh_retains_refresh_token_and_scopes(monkeypatch):
    values = token_data()
    values["expires_in"] = 0
    google._save_tokens(values, google._generation)
    request = AsyncMock(return_value={"access_token": "new-test-token", "token_type": "Bearer", "expires_in": 3600})
    monkeypatch.setattr(google, "_request", request)
    headers = asyncio.run(google._access(google.SCOPES["gmail"], google._generation))
    assert headers == {"Authorization": "Bearer new-test-token"}
    assert google._load(google.TOKENS)["refresh_token"] == "test-refresh-token"
    assert request.call_args.kwargs["data"]["grant_type"] == "refresh_token"


def test_provider_preview_shapes_and_limits(monkeypatch):
    google._save_tokens(token_data(), google._generation)
    request = AsyncMock(side_effect=[
        {"messages": [{"id": "abc"}], "nextPageToken": "more"},
        {"payload": {"headers": [{"name": "Subject", "value": "Test subject"}]}, "snippet": "Preview"},
        {"items": [{"summary": "All day", "start": {"date": "2026-10-18"}, "end": {"date": "2026-10-19"}}]},
    ])
    monkeypatch.setattr(google, "_request", request)
    mail = asyncio.run(google.messages())
    assert mail["messages"][0]["subject"] == "Test subject" and mail["more_available"]
    events = asyncio.run(google.events())
    assert events["events"][0]["start"] == "2026-10-18"
    assert request.call_args_list[0].kwargs["params"]["maxResults"] == 10
    assert request.call_args_list[2].kwargs["params"]["maxResults"] == 25


def test_offline_blocks_before_dns(monkeypatch):
    google._save_tokens(token_data(), google._generation)
    monkeypatch.setattr(google.egress_guard, "offline", True)
    from app.core import network_utils
    monkeypatch.setattr(network_utils, "resolve_and_validate_url", lambda *_: pytest.fail("Offline must block DNS"))
    with pytest.raises(google.GoogleError, match="Offline"):
        asyncio.run(google.messages())


def test_lock_race_discards_provider_result(monkeypatch):
    class Client:
        def __init__(self, **_): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def safe_request(self, *_args, **kwargs):
            assert kwargs["max_redirects"] == 0
            google.cancel("lock")
            return httpx.Response(200, json=token_data())
    monkeypatch.setattr(google, "SafeAsyncClient", Client)
    with pytest.raises(google.GoogleError, match="cancelled"):
        asyncio.run(google._request("POST", "https://oauth2.googleapis.com/token", google._generation))
    assert secrets_store.get_secret(google.TOKENS) is None


def test_routes_require_session_unlock_and_pin(monkeypatch):
    from app.main import app
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", TOKEN)
    web = TestClient(app)
    assert web.get("/api/workspace/google/status").status_code == 422
    assert web.get("/api/workspace/google/status", headers={"X-Sentinel-Session": "wrong"}).status_code == 401
    status = web.get("/api/workspace/google/status", headers=HEADERS)
    assert status.status_code == 200 and "test-client-secret" not in status.text
    monkeypatch.setattr(google.vault, "pin_fresh", lambda: False)
    assert web.post("/api/workspace/google/start", headers=HEADERS, json={}).status_code == 403
    monkeypatch.setattr(google.vault, "is_unlocked", lambda: False)
    assert web.get("/api/workspace/google/status", headers=HEADERS).status_code == 423
