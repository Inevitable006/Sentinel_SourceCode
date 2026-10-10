"""F11/F12: the connection goes to the validated address, and large bodies are stopped while downloading."""
import asyncio
import socket

import httpcore
import httpx
import pytest

from app.core import network_utils
from app.core.egress import tool_context
from app.core.network_utils import SafeAsyncClient, ResponseTooLarge


def test_rebinding_resolver_cannot_redirect_the_connection(monkeypatch):
    """First lookup (validation) says public, any later lookup says loopback.
    The TCP connect must go to the validated public address and nowhere else."""
    answers = iter(["93.184.216.34"] + ["127.0.0.1"] * 10)
    def resolver(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), port))]
    monkeypatch.setattr(network_utils.socket, "getaddrinfo", resolver)

    connected = []
    class Recorder:
        async def connect_tcp(self, host, port, **kwargs):
            connected.append((host, port))
            raise httpcore.ConnectError("stop here (test)")
    client = SafeAsyncClient()
    client._pinned_backend._inner = Recorder()

    async def go():
        with tool_context("test_tool", True):
            async with client:
                await client.safe_request("GET", "https://rebind.example/")
    with pytest.raises(httpx.ConnectError):
        asyncio.run(go())
    assert connected == [("93.184.216.34", 443)]


def test_unvalidated_host_is_refused_by_the_transport():
    backend = network_utils._PinnedBackend()
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(backend.connect_tcp("not-validated.example", 443))


def test_oversized_body_is_stopped(monkeypatch):
    monkeypatch.setattr(network_utils, "resolve_and_validate_url", lambda url: (True, "93.184.216.34", None))
    def handler(request):
        return httpx.Response(200, content=b"x" * (64 * 1024))
    async def go():
        with tool_context("test_tool", True):
            async with SafeAsyncClient(transport=httpx.MockTransport(handler)) as c:
                small = await c.safe_request("GET", "https://big.example/", max_bytes=1024 * 1024)
                assert len(small.content) == 64 * 1024
                await c.safe_request("GET", "https://big.example/", max_bytes=1024)
    with pytest.raises(ResponseTooLarge):
        asyncio.run(go())
