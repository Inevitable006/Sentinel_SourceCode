"""
Egress guard (Phase 1, step 1.1): nothing leaves the PC unless its host is allowlisted or
the request comes from a tool that declared network_access; offline mode blocks everything;
every decision is logged without paths, queries or bodies.
"""
import asyncio
import json
import socket
from unittest.mock import patch

import httpx
import pytest

from app.core import egress
from app.core.egress import EgressBlocked, EgressGuard, tool_context
from app.core.network_utils import SafeAsyncClient

SAFE_DNS = (True, "93.184.215.14", None)


@pytest.fixture()
def guard(tmp_path):
    g = EgressGuard(log_path=tmp_path / "egress.jsonl", policy_path=tmp_path / "network_policy.json")
    with patch("app.core.network_utils.egress_guard", g):
        yield g


def _client(handler):
    return SafeAsyncClient(transport=httpx.MockTransport(handler))


def _ok(request):
    return httpx.Response(200, text="hello")


# ── decisions ───────────────────────────────────────────────────

def test_allowlisted_host_is_allowed_without_a_tool(guard):
    guard.record_result(guard.check("GET", "html.duckduckgo.com"), status=200, bytes_in=10)
    last = guard.recent(1)[0]
    assert (last["decision"], last["tool"], last["status"]) == ("allowed", None, 200)


def test_unknown_host_outside_a_tool_is_blocked(guard):
    with pytest.raises(EgressBlocked, match="unexpected outbound"):
        guard.check("GET", "evil.example")
    assert guard.recent(1)[0]["decision"] == "blocked"
    assert guard.status()["blocked_total"] == 1


def test_network_tool_may_reach_other_hosts(guard):
    with tool_context("fetch_url", network_allowed=True):
        rec = guard.check("GET", "en.wikipedia.org")
    guard.record_result(rec, status=200)
    assert guard.recent(1)[0]["tool"] == "fetch_url"


def test_tool_without_network_access_is_blocked(guard):
    with tool_context("get_system_telemetry", network_allowed=False), pytest.raises(EgressBlocked):
        guard.check("GET", "en.wikipedia.org")


def test_offline_mode_blocks_everything_and_persists(guard, tmp_path):
    guard.set_offline(True)
    with tool_context("fetch_url", True), pytest.raises(EgressBlocked, match="offline"):
        guard.check("GET", "html.duckduckgo.com")
    policy = tmp_path / "network_policy.json"
    assert EgressGuard(log_path=tmp_path / "a.jsonl", policy_path=policy).offline is True
    guard.set_offline(False)
    assert EgressGuard(log_path=tmp_path / "b.jsonl", policy_path=policy).offline is False


def test_unreadable_policy_fails_closed(tmp_path):
    (tmp_path / "network_policy.json").write_text("{not json", encoding="utf-8")
    assert EgressGuard(log_path=tmp_path / "e.jsonl", policy_path=tmp_path / "network_policy.json").offline is True


def test_extra_allowed_hosts_from_policy(tmp_path):
    (tmp_path / "network_policy.json").write_text(
        json.dumps({"offline": False, "allowed_hosts": ["API.Example.com."]}), encoding="utf-8")
    g = EgressGuard(log_path=tmp_path / "e.jsonl", policy_path=tmp_path / "network_policy.json")
    g.record_result(g.check("GET", "api.example.com"))
    assert "api.example.com" in g.allowlist()


def test_log_rotates(guard, monkeypatch):
    monkeypatch.setattr(egress, "LOG_MAX_BYTES", 200)
    for _ in range(10):
        guard.record_result(guard.check("GET", "html.duckduckgo.com"), status=200)
    assert guard._log_path.with_name("egress.jsonl.1").exists()


# ── through the real HTTP client ────────────────────────────────

def test_client_logs_host_but_never_path_or_query(guard):
    async def go():
        async with _client(_ok) as c:
            with patch("app.core.network_utils.resolve_and_validate_url", return_value=SAFE_DNS):
                return await c.safe_request("GET", "https://html.duckduckgo.com/html/?q=my+secret+diagnosis")
    assert asyncio.run(go()).status_code == 200
    raw = guard._log_path.read_text(encoding="utf-8")
    assert "html.duckduckgo.com" in raw
    assert "secret" not in raw and "diagnosis" not in raw and "/html" not in raw
    last = guard.recent(1)[0]
    assert last["status"] == 200 and last["bytes_in"] == 5 and "ms" in last


def test_blocked_host_is_never_resolved(guard):
    async def go():
        async with _client(_ok) as c:
            with patch("app.core.network_utils.resolve_and_validate_url") as dns:
                with pytest.raises(EgressBlocked):
                    await c.safe_request("GET", "https://tracker.example/pixel")
                dns.assert_not_called()
    asyncio.run(go())


def test_redirect_to_an_unapproved_host_is_blocked(guard):
    def handler(request):
        if request.url.host == "html.duckduckgo.com":
            return httpx.Response(302, headers={"Location": "https://elsewhere.example/landing"})
        return httpx.Response(200, text="must not get here")

    async def go():
        async with _client(handler) as c:
            with patch("app.core.network_utils.resolve_and_validate_url", return_value=SAFE_DNS):
                with pytest.raises(EgressBlocked):
                    await c.safe_request("GET", "https://html.duckduckgo.com/html/?q=x")
    asyncio.run(go())
    assert [e["decision"] for e in guard.recent(2)] == ["blocked", "allowed"]   # newest first


def test_ssrf_rejection_is_logged_as_blocked(guard):
    async def go():
        async with _client(_ok) as c:
            with tool_context("fetch_url", True), patch(
                    "app.core.network_utils.resolve_and_validate_url",
                    return_value=(False, None, "IP 10.0.0.1 is in a restricted range.")):
                with pytest.raises(ValueError, match="SSRF"):
                    await c.safe_request("GET", "https://intranet.example/")
    asyncio.run(go())
    last = guard.recent(1)[0]
    assert last["decision"] == "blocked" and "SSRF" in last["reason"]


# ── the secure runner marks which tool is running ───────────────

def test_secure_runner_sets_tool_context():
    from app.core.secure_runner import secure_runner
    from app.core.tool_registry import RiskTier, ToolDefinition, ToolSchema, tool_registry
    seen = {}

    def probe_net():
        seen["net"] = egress.current_tool()
        return "ok"

    def probe_local():
        seen["local"] = egress.current_tool()
        return "ok"

    tool_registry.register(ToolDefinition(tool_schema=ToolSchema(
        name="_t_net", description="t", risk_tier=RiskTier.TIER_1, parameters={},
        required_capabilities=["network_access"]), executor=probe_net))
    tool_registry.register(ToolDefinition(tool_schema=ToolSchema(
        name="_t_local", description="t", risk_tier=RiskTier.TIER_1, parameters={}), executor=probe_local))
    try:
        assert secure_runner.execute("_t_net", {}, "s1")["status"] == "success"
        assert secure_runner.execute("_t_local", {}, "s1")["status"] == "success"
    finally:
        tool_registry.tools.pop("_t_net", None)
        tool_registry.tools.pop("_t_local", None)
    assert seen["net"] == {"tool": "_t_net", "network": True}
    assert seen["local"] == {"tool": "_t_local", "network": False}
    assert egress.current_tool() is None


def test_search_web_declares_network_access():
    import app.core.tools  # noqa: F401  (registers the core tools)
    from app.core.tool_registry import tool_registry
    assert "network_access" in tool_registry.get_tool("search_web").tool_schema.required_capabilities


# ── API ─────────────────────────────────────────────────────────

def test_egress_api_requires_the_session_token(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as main
    g = EgressGuard(log_path=tmp_path / "e.jsonl", policy_path=tmp_path / "p.json")
    monkeypatch.setattr(main, "egress_guard", g)
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "t0k")
    c = TestClient(main.app)
    assert c.get("/api/egress/status").status_code == 422                                   # no token
    assert c.get("/api/egress/status", headers={"x-sentinel-session": "nope"}).status_code == 401
    h = {"x-sentinel-session": "t0k"}
    assert c.get("/api/egress/status", headers=h).json()["offline"] is False
    assert c.post("/api/egress/offline", json={"enabled": True}, headers=h).json()["offline"] is True
    assert g.offline is True
    assert c.get("/api/egress/log", headers=h).json() == {"events": []}


# ── the test suite itself can't reach the internet ──────────────

def test_tests_cannot_reach_the_internet():
    with pytest.raises(OSError):
        socket.create_connection(("example.com", 443), timeout=1)
    with pytest.raises(OSError):
        socket.getaddrinfo("example.com", 443)
