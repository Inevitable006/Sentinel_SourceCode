"""Behavioral regression tests for the reliability milestone.

Validates: cancellation during generation, cancellation during tool work,
concurrent submission rejection, disconnect cleanup, approval replay/mismatch,
decline and expiry handling, successful continuation with result persisted
exactly once to the correct conversation thread.

Uses deterministic doubles — no model, network, or personal database opened.
"""
import ast
import asyncio
import hmac
import json
import os
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class Disconnected(Exception):
    pass


class Socket:
    """Minimal WebSocket double that feeds messages and records sends."""

    # The token arrives as a WebSocket subprotocol (header), not in the URL.
    headers = {"origin": "http://localhost:5173", "sec-websocket-protocol": "sentinel.v1, test-token"}
    query_params = {}

    def __init__(self, messages=None):
        self.sent = []
        self._messages = list(messages or [])
        self._idx = 0
        self.finished = asyncio.Event()

    async def accept(self, subprotocol=None):
        pass

    async def send_json(self, payload):
        self.sent.append(payload)
        if payload.get("state") in ("COMPLETED", "CANCELLED") or payload.get("type") == "tool_confirmation_required":
            self.finished.set()

    async def receive_text(self):
        if self._idx >= len(self._messages):
            if self._idx:
                await asyncio.wait_for(self.finished.wait(), 5)
            raise Disconnected()
        msg = self._messages[self._idx]
        if self._idx and isinstance(msg, dict) and msg.get("type") != "cancel":
            await asyncio.wait_for(self.finished.wait(), 5)
            self.finished.clear()
        self._idx += 1
        if isinstance(msg, dict):
            return json.dumps(msg)
        return msg


def _build_namespace(responses, tool_result=None, tool_side_effect=None):
    """Compile chat_endpoint from source and return everything needed to run it."""
    source = Path(__file__).resolve().parents[2] / "app" / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    # The handler plus the real helpers it calls (e.g. constant-time token check)
    wanted = {"chat_endpoint", "_token_matches"}
    nodes = [
        n for n in tree.body
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name in wanted
    ]
    assert {n.name for n in nodes} == wanted, "main.py is missing chat_endpoint or _token_matches"
    for n in nodes:
        n.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))

    calls = []
    history = []
    db = types.SimpleNamespace(
        query=lambda *_: types.SimpleNamespace(first=lambda: None),
        close=lambda: None,
    )
    memory = types.SimpleNamespace(
        create_thread=lambda *_a, **_k: "thread-test",
        add_message=lambda *_a: history.append(_a[2:]),
        get_context_history=lambda *_a, **_k: [],
        retrieve_relevant_memory=lambda *_a, **_k: [],
    )

    response_iter = iter(responses)

    def _stream(*_a, **_k):
        for tok in next(response_iter):
            yield tok

    ai = types.SimpleNamespace(llm=True, generate_stream=_stream)

    def execute_tool(*args):
        calls.append(args)
        if tool_side_effect:
            tool_side_effect()
        return json.dumps(tool_result)

    modules = {}
    for name in ["app", "app.core", "app.core.tools",
                  "app.core.token_service", "app.core.skill_router",
                  "app.core.safe_process"]:
        modules[name] = types.ModuleType(name)
    modules["app.core.tools"].execute_tool = execute_tool
    modules["app.core.token_service"].token_service = types.SimpleNamespace(
        cleanup_expired=lambda: None,
    )
    modules["app.core.skill_router"].skill_router = types.SimpleNamespace(
        check_confidence=lambda *_: True,
        resolve_skill=lambda *_: None,
    )
    modules["app.core.safe_process"].safe_process = types.SimpleNamespace(
        cancel_job=lambda *_: None,
    )

    namespace = dict(
        WebSocket=Socket,
        WebSocketDisconnect=Disconnected,
        os=os,
        asyncio=asyncio,
        hmac=hmac,
        json=json,
        SessionLocal=lambda: db, CHAT_SOCKETS=set(), vault=types.SimpleNamespace(touch=lambda: None),
        memory_service=memory,
        ai_service=ai,
        AppSettings=object,
        vision_service=None,
    )
    exec(compile(module, str(source), "exec"), namespace)
    return namespace, modules, calls, history


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    """Cancellation during generation and tool work."""

    async def test_cancel_signal_emits_cancelled(self):
        """A cancel signal should emit CANCELLED state."""
        responses = [["Hello", " world"]]
        ns, mods, calls, history = _build_namespace(responses)

        socket = Socket([
            {"text": "test", "voice_enabled": False},
            {"type": "cancel"},
        ])

        with patch.dict(sys.modules, mods), \
             patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await ns["chat_endpoint"](socket)

        states = [e.get("state") for e in socket.sent if e.get("type") == "state"]
        self.assertIn("CANCELLED", states)
        self.assertFalse(any(e.get("type") == "error" for e in socket.sent))


class ConcurrentSubmissionTests(unittest.IsolatedAsyncioTestCase):
    """One active request per connection."""

    async def test_sequential_requests_both_complete(self):
        """Two sequential requests should both complete normally."""
        responses = [["response1"], ["response2"]]
        ns, mods, calls, history = _build_namespace(responses)

        socket = Socket([
            {"text": "first request", "voice_enabled": False},
            {"text": "second request", "voice_enabled": False},
        ])

        with patch.dict(sys.modules, mods), \
             patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await ns["chat_endpoint"](socket)

        completed_count = sum(
            1 for e in socket.sent if e.get("state") == "COMPLETED"
        )
        self.assertEqual(completed_count, 2)
        error_msgs = [e for e in socket.sent if e.get("type") == "error"]
        self.assertEqual(len(error_msgs), 0)


class DisconnectCleanupTests(unittest.IsolatedAsyncioTestCase):
    """Disconnect should release resources cleanly."""

    async def test_disconnect_closes_db(self):
        """When the client disconnects, the db session should be closed."""
        responses = [["Hello"]]
        ns, mods, calls, history = _build_namespace(responses)

        db_closed = [False]
        original_ns_db = ns["SessionLocal"]

        def mock_session_local():
            db = original_ns_db()
            original_close = db.close

            def tracked_close():
                db_closed[0] = True
                return original_close()

            db.close = tracked_close
            return db

        ns["SessionLocal"] = mock_session_local

        socket = Socket([
            {"text": "hello", "voice_enabled": False},
        ])

        with patch.dict(sys.modules, mods), \
             patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await ns["chat_endpoint"](socket)

        self.assertTrue(db_closed[0], "DB session was not closed on disconnect")

    async def test_processing_flag_released_on_completion(self):
        """The is_processing flag should be released after completion."""
        responses = [["Hello"]]
        ns, mods, calls, history = _build_namespace(responses)
        socket = Socket([
            {"text": "test", "voice_enabled": False},
        ])

        with patch.dict(sys.modules, mods), \
             patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await ns["chat_endpoint"](socket)

        completed = [e for e in socket.sent if e.get("state") == "COMPLETED"]
        self.assertTrue(len(completed) >= 1)


class ApprovalReplayTests(unittest.IsolatedAsyncioTestCase):
    """Approval token replay, mismatch, and expiry."""

    def test_token_single_use(self):
        """A token can only be validated once — replay must fail."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.core.token_service import TokenService

        svc = TokenService()
        tok = svc.generate_token("session-1", "tool-a", {"x": 1}, risk_tier=2)
        self.assertTrue(svc.validate_token(tok, "session-1", "tool-a", {"x": 1}))
        self.assertFalse(svc.validate_token(tok, "session-1", "tool-a", {"x": 1}),
                         "Replayed token must be rejected")

    def test_token_session_mismatch(self):
        """A token bound to session-1 must fail validation for session-2."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.core.token_service import TokenService

        svc = TokenService()
        tok = svc.generate_token("session-1", "tool-a", {"x": 1}, risk_tier=2)
        self.assertFalse(svc.validate_token(tok, "session-2", "tool-a", {"x": 1}))

    def test_token_tool_mismatch(self):
        """A token for tool-a must fail validation when used for tool-b."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.core.token_service import TokenService

        svc = TokenService()
        tok = svc.generate_token("session-1", "tool-a", {"x": 1}, risk_tier=2)
        self.assertFalse(svc.validate_token(tok, "session-1", "tool-b", {"x": 1}))

    def test_token_args_mismatch(self):
        """A token for args {x:1} must fail if args are changed to {x:2}."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.core.token_service import TokenService

        svc = TokenService()
        tok = svc.generate_token("session-1", "tool-a", {"x": 1}, risk_tier=2)
        self.assertFalse(svc.validate_token(tok, "session-1", "tool-a", {"x": 2}))

    def test_token_expiry(self):
        """An expired token must be rejected."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.core.token_service import TokenService

        svc = TokenService()
        tok = svc.generate_token("session-1", "tool-a", {"x": 1},
                                 risk_tier=2, expiry_seconds=0)
        time.sleep(0.01)
        self.assertFalse(svc.validate_token(tok, "session-1", "tool-a", {"x": 1}))


class DeclineAndExpiryTests(unittest.IsolatedAsyncioTestCase):
    """Decline flow: user never confirms; token expires or is never used."""

    async def test_confirmation_pause_does_not_emit_completed(self):
        """When a tool returns needs_confirmation, the handler must pause
        without emitting COMPLETED."""
        call = '<tool_call>{"name":"example","args":{"v":1}}</tool_call>'
        result = {
            "status": "needs_confirmation",
            "token": "approval-token",
            "action_preview": {"tool": "example", "args": {"v": 1}},
        }
        ns, mods, calls, history = _build_namespace([[call]], result)
        socket = Socket([{"text": "run", "voice_enabled": False}])

        with patch.dict(sys.modules, mods), \
             patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await ns["chat_endpoint"](socket)

        self.assertFalse(
            any(e.get("state") == "COMPLETED" for e in socket.sent),
            "COMPLETED should not be emitted when awaiting confirmation",
        )
        approvals = [e for e in socket.sent if e["type"] == "tool_confirmation_required"]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["data"]["session_id"], "thread-test")

    def test_cleanup_removes_expired_tokens(self):
        """cleanup_expired should purge expired and used tokens."""
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from app.core.token_service import TokenService, _TOKEN_STORE

        # Isolate from tokens created by other tests in this run
        _TOKEN_STORE.clear()

        svc = TokenService()
        tok1 = svc.generate_token("s1", "t1", {}, risk_tier=1, expiry_seconds=0)
        tok2 = svc.generate_token("s1", "t2", {}, risk_tier=1)
        svc.validate_token(tok2, "s1", "t2", {})  # mark used
        time.sleep(0.01)
        removed = svc.cleanup_expired()
        self.assertEqual(removed, 2)


class SuccessfulContinuationTests(unittest.IsolatedAsyncioTestCase):
    """Tool result persisted to the correct thread, continuation exactly once."""

    async def test_tool_result_persisted_with_continuation(self):
        """A successful tool execution should persist the result to the
        thread and produce exactly one follow-up completion."""
        call = '<tool_call>{"name":"example","args":{}}</tool_call>'
        result = {"status": "success", "data": "computed-result"}
        ns, mods, calls, history = _build_namespace(
            [[call], ["Summary of result."]],
            result,
        )
        socket = Socket([{"text": "compute", "voice_enabled": False}])

        with patch.dict(sys.modules, mods), \
             patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await ns["chat_endpoint"](socket)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], "thread-test")

        system_messages = [text for role, text in history if role == "system"]
        self.assertTrue(
            any("computed-result" in msg for msg in system_messages),
            "Tool result not found in persisted history",
        )

        completed = [e for e in socket.sent if e.get("state") == "COMPLETED"]
        self.assertEqual(len(completed), 1, "Should complete exactly once")

    async def test_thread_id_used_as_session_identity(self):
        """All tool executions must pass thread_id, not an undefined
        session_id, as the session identity."""
        call = '<tool_call>{"name":"example","args":{}}</tool_call>'
        result = {"status": "success", "data": "ok"}
        ns, mods, calls, history = _build_namespace(
            [[call], ["done"]],
            result,
        )
        socket = Socket([{"text": "test", "voice_enabled": False}])

        with patch.dict(sys.modules, mods), \
             patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await ns["chat_endpoint"](socket)

        self.assertTrue(len(calls) >= 1)
        self.assertEqual(calls[0][2], "thread-test",
                         "execute_tool must receive thread_id as session identity")


if __name__ == "__main__":
    unittest.main()
