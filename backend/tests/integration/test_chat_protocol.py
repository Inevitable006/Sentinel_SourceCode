"""Exercise the real chat handler with deterministic model and tool doubles.

Uses only the standard library; no model, network, or personal database is opened.
"""
import ast
import asyncio
import hmac
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class Disconnected(Exception):
    pass


class Socket:
    headers = {"origin": "http://localhost:5173"}
    query_params = {"token": "test-token"}

    def __init__(self):
        self.sent = []
        self.received = False

    async def accept(self):
        pass

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive_text(self):
        if self.received:
            raise Disconnected()
        self.received = True
        return json.dumps({"text": "test request", "voice_enabled": False})


class ChatProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def run_chat(self, responses, tool_result=None):
        source = Path(__file__).resolve().parents[2] / "app" / "main.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        wanted = {"chat_endpoint", "_token_matches"}
        nodes = [n for n in tree.body
                 if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name in wanted]
        assert {n.name for n in nodes} == wanted, "main.py is missing chat_endpoint or _token_matches"
        handler = next(n for n in nodes if n.name == "chat_endpoint")
        handler.decorator_list = []
        for n in nodes:
            n.decorator_list = []
        module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
        calls = []
        history = []
        db = types.SimpleNamespace(query=lambda *_: types.SimpleNamespace(first=lambda: None), close=lambda: None)
        memory = types.SimpleNamespace(
            create_thread=lambda *_args, **_kwargs: "thread-test",
            add_message=lambda *_args: history.append(_args[2:]),
            get_context_history=lambda *_args, **_kwargs: [],
            retrieve_relevant_memory=lambda *_args, **_kwargs: [],
        )
        response_iter = iter(responses)
        ai = types.SimpleNamespace(llm=True, generate_stream=lambda *_args, **_kwargs: iter(next(response_iter)))

        def execute_tool(*args):
            calls.append(args)
            return json.dumps(tool_result)

        modules = {}
        for name in ["app", "app.core", "app.core.tools", "app.core.token_service", "app.core.skill_router", "app.core.safe_process"]:
            modules[name] = types.ModuleType(name)
        modules["app.core.tools"].execute_tool = execute_tool
        modules["app.core.token_service"].token_service = types.SimpleNamespace(cleanup_expired=lambda: None)
        modules["app.core.skill_router"].skill_router = types.SimpleNamespace(check_confidence=lambda *_: True, resolve_skill=lambda *_: None)
        modules["app.core.safe_process"].safe_process = types.SimpleNamespace(cancel_job=lambda *_: None)
        namespace = dict(WebSocket=Socket, WebSocketDisconnect=Disconnected, os=os, asyncio=asyncio, hmac=hmac,
                         json=json, SessionLocal=lambda: db, memory_service=memory, ai_service=ai,
                         AppSettings=object, vision_service=None)
        exec(compile(module, str(source), "exec"), namespace)
        socket = Socket()
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"SENTINEL_SESSION_TOKEN": "test-token"}):
            await namespace["chat_endpoint"](socket)
        return socket.sent, calls, history

    async def test_plain_reply_streams_once(self):
        events, calls, _ = await self.run_chat([["Hello", " world"]])
        self.assertEqual(sum(e["type"] == "reply_start" for e in events), 1)
        self.assertEqual("".join(e["token"] for e in events if e["type"] == "reply_chunk"), "Hello world")
        self.assertEqual(events[-1], {"type": "state", "state": "COMPLETED"})
        self.assertFalse(calls)

    async def test_serialized_confirmation_pauses_with_connection_identity(self):
        call = '<tool_call>{"name":"example","args":{"value":1}}</tool_call>'
        result = {"status": "needs_confirmation", "token": "approval-token", "action_preview": {"tool": "example", "args": {"value": 1}}}
        events, calls, _ = await self.run_chat([[call]], result)
        self.assertEqual(calls[0][2], "thread-test")
        approvals = [e for e in events if e["type"] == "tool_confirmation_required"]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["data"]["session_id"], "thread-test")
        self.assertFalse(any(e["type"] == "error" for e in events))
        self.assertFalse(any(e.get("state") == "COMPLETED" for e in events))

    async def test_successful_tool_continues_to_summary(self):
        call = '<tool_call>{"name":"example","args":{}}</tool_call>'
        events, calls, history = await self.run_chat([[call], ["The result is ready."]], {"status": "success", "data": "ok"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(events[-1]["state"], "COMPLETED")
        self.assertTrue(any("ok" in text for role, text in history if role == "system"))


if __name__ == "__main__":
    unittest.main()
