"""
Shared pytest setup for the Sentinel backend.

Every test run gets its own throwaway data directory, so tests never read or
write your real chat history, memory DB, audit log or model registry
(%APPDATA%\\sentinel). This has to happen before any `app.*` module is
imported, because app.core.paths resolves the data directory at import time.
"""
import os
import shutil
import tempfile

import pytest

_TEST_DATA_ROOT = tempfile.mkdtemp(prefix="sentinel_test_data_")
os.environ["APPDATA"] = _TEST_DATA_ROOT
# Some modules (e.g. the audit logger) write during import, before any fixture runs.
for _sub in ("models", "logs"):
    os.makedirs(os.path.join(_TEST_DATA_ROOT, "sentinel", _sub), exist_ok=True)


# ── No internet in tests ─────────────────────────────────────────
# Resolving or connecting to any non-loopback host fails loudly, so a test can never
# leak data or silently depend on the network. Loopback (TestClient, local servers) works.
import asyncio
import ipaddress
import socket

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo
_real_create_connection = asyncio.BaseEventLoop.create_connection


def _is_loopback(host) -> bool:
    if host is None:
        return True
    h = str(host).strip().strip("[]").lower()
    if h in ("", "localhost") or h.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_loopback or ip.is_unspecified
    except ValueError:
        return False


def _is_ip_literal(host) -> bool:
    try:
        ipaddress.ip_address(str(host).strip().strip("[]"))
        return True
    except ValueError:
        return False


def _blocked(host):
    return OSError(f"[test network guard] connection to {host!r} blocked: tests must not use the internet")


def _guarded_connect(self, address):
    if isinstance(address, tuple) and not _is_loopback(address[0]):
        raise _blocked(address[0])
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if isinstance(address, tuple) and not _is_loopback(address[0]):
        raise _blocked(address[0])
    return _real_connect_ex(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_loopback(host) and not _is_ip_literal(host):
        raise socket.gaierror(f"[test network guard] DNS lookup for {host!r} blocked: tests must not use the internet")
    return _real_getaddrinfo(host, *args, **kwargs)


async def _guarded_create_connection(self, protocol_factory, host=None, port=None, *args, **kwargs):
    if host is not None and not _is_loopback(host):
        raise _blocked(host)
    return await _real_create_connection(self, protocol_factory, host, port, *args, **kwargs)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
socket.getaddrinfo = _guarded_getaddrinfo
asyncio.BaseEventLoop.create_connection = _guarded_create_connection


_TEST_DB_KEY = os.urandom(32)   # the throwaway test database is encrypted exactly like the real one


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir():
    from app.core.paths import SENTINEL_DATA_DIR, ensure_paths

    assert str(SENTINEL_DATA_DIR).startswith(_TEST_DATA_ROOT), "tests must never touch the real data directory"
    ensure_paths()
    # Open the encrypted test database (the app opens it at unlock) and create the schema.
    from app.db.database import close_database, init_db, open_database

    open_database(_TEST_DB_KEY)
    init_db()
    yield
    close_database()
    shutil.rmtree(_TEST_DATA_ROOT, ignore_errors=True)


@pytest.fixture()
def locked_db():
    """Closes the test database for one test (as if Sentinel were locked), then reopens it."""
    from app.db.database import close_database, open_database

    close_database()
    yield
    open_database(_TEST_DB_KEY)


@pytest.fixture()
def reopen_db():
    """For tests that close the database themselves: reopens it afterwards."""
    from app.db.database import is_open, open_database

    yield
    if not is_open():
        open_database(_TEST_DB_KEY)
