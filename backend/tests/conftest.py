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


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir():
    from app.core.paths import SENTINEL_DATA_DIR, ensure_paths

    assert str(SENTINEL_DATA_DIR).startswith(_TEST_DATA_ROOT), "tests must never touch the real data directory"
    ensure_paths()
    # Create the DB schema (tables + memory FTS index) the app creates at startup.
    from app.db.database import engine, init_db

    init_db()
    yield
    engine.dispose()
    shutil.rmtree(_TEST_DATA_ROOT, ignore_errors=True)
