"""
Sentinel's database: SQLite encrypted with SQLCipher.

The database stays CLOSED while Sentinel is locked. The vault (app.core.vault) opens it with
the 32-byte data key after you unlock, and closes it when Sentinel locks. While it is closed,
SessionLocal() raises DatabaseLocked, which the API turns into HTTP 423.

On first setup, an old unencrypted database (jarvis_memory.db) is copied into the encrypted
one with SQLCipher's sqlcipher_export, verified table by table, and cleaned of rows that old
test runs left behind. The old file is kept untouched until you delete it from Settings.
"""
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.paths import SENTINEL_DATA_DIR

ENCRYPTED_DB_PATH = SENTINEL_DATA_DIR / "sentinel.db"      # SQLCipher, encrypted
LEGACY_DB_PATH = SENTINEL_DATA_DIR / "jarvis_memory.db"     # old unencrypted database

Base = declarative_base()


class DatabaseLocked(RuntimeError):
    """The encrypted database is closed because Sentinel is locked."""


class MigrationError(RuntimeError):
    pass


_state_lock = threading.RLock()
_engine = None
_connections: set = set()   # every open DBAPI connection made with the key
_Session = sessionmaker(autocommit=False, autoflush=False)


def _url(path: Path, key: bytes) -> URL:
    # SQLCipher raw key syntax: pragma key = "x'<64 hex chars>'" (no password KDF; the key is
    # already random). The URL object masks the password in any repr or log line.
    return URL.create("sqlite+pysqlcipher", password=f"x'{key.hex()}'", database=str(path))


def open_database(key: bytes, path: Optional[Path] = None) -> None:
    """Open (or create) the encrypted database with the data key. Raises if the key is wrong."""
    global _engine
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise ValueError("the data key must be 32 bytes")
    with _state_lock:
        close_database()
        eng = create_engine(_url(Path(path or ENCRYPTED_DB_PATH), bytes(key)),
                            connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _track(dbapi_conn, _record):
            _connections.add(dbapi_conn)

        @event.listens_for(eng, "close")
        def _untrack(dbapi_conn, _record):
            _connections.discard(dbapi_conn)

        @event.listens_for(eng, "close_detached")
        def _untrack_detached(dbapi_conn):
            _connections.discard(dbapi_conn)

        try:
            with eng.connect() as conn:            # SQLCipher only notices a wrong key on first read
                conn.execute(text("SELECT count(*) FROM sqlite_master"))
        except Exception:
            eng.dispose()
            raise
        _engine = eng
        _Session.configure(bind=eng)


def close_database() -> None:
    """Close the database. Connections still held by running code are closed too, so nothing
    can keep reading or writing after Sentinel locks."""
    global _engine
    with _state_lock:
        if _engine is not None:
            _engine.dispose()
        for conn in list(_connections):
            try:
                conn.close()
            except Exception:
                pass
        _connections.clear()
        _engine = None
        _Session.configure(bind=None)


def is_open() -> bool:
    return _engine is not None


def get_engine():
    if _engine is None:
        raise DatabaseLocked("Sentinel is locked. Unlock it to use memory and chat history.")
    return _engine


def SessionLocal():
    """Same call style as before (db = SessionLocal()), but refuses while Sentinel is locked."""
    if _engine is None:
        raise DatabaseLocked("Sentinel is locked. Unlock it to use memory and chat history.")
    return _Session()


# Full-text index for personal memory, kept in sync by triggers.
_FTS_SETUP = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_memory_items USING fts5(
        id UNINDEXED,
        content
    )
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items
    BEGIN
        INSERT INTO fts_memory_items(id, content) VALUES (new.id, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items
    BEGIN
        UPDATE fts_memory_items SET content = new.content WHERE id = old.id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items
    BEGIN
        DELETE FROM fts_memory_items WHERE id = old.id;
    END
    """,
    # Index any memories written before the index existed.
    """
    INSERT INTO fts_memory_items(id, content)
    SELECT id, content FROM memory_items
    WHERE id NOT IN (SELECT id FROM fts_memory_items)
    """,
]


def init_db():
    """Create all tables plus the memory FTS index and triggers. Safe to call repeatedly."""
    from app.db import models  # noqa: F401  (registers the tables on Base.metadata)

    eng = get_engine()
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        for stmt in _FTS_SETUP:
            conn.execute(text(stmt))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def open_for_vault(key: bytes, first_setup: bool = False) -> Dict:
    """Called by the vault: on first setup, migrate the old database first; then open + init."""
    report: Dict = {}
    if first_setup:
        report = migrate_legacy_db(key)
    open_database(key)
    init_db()
    return report


# ── one-time migration from the old unencrypted database ────────

# Rows that old test runs (before tests were isolated) wrote into the real database.
TEST_MEMORY_CONTENTS = (
    "I like pizza.",
    "My favorite color is neon green.",
    "My super secret password is password123.",
    "my favourite editor is neovim",
)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _table_counts(conn) -> Dict[str, int]:
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {n: conn.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in names}


def _remove_test_rows(conn) -> Dict[str, int]:
    removed = {"test_memories": 0, "test_threads": 0, "empty_threads": 0}
    try:
        marks = ",".join("?" * len(TEST_MEMORY_CONTENTS))
        removed["test_memories"] = conn.execute(
            f"DELETE FROM memory_items WHERE content IN ({marks})", TEST_MEMORY_CONTENTS).rowcount
    except sqlite3.Error:
        pass
    try:
        test_threads = [r[0] for r in conn.execute(
            """SELECT t.id FROM threads t
               WHERE (SELECT count(*) FROM messages m WHERE m.thread_id = t.id) = 1
                 AND EXISTS (SELECT 1 FROM messages m WHERE m.thread_id = t.id
                             AND m.role = 'user' AND m.content = 'What is Python?')""")]
        empty_threads = [r[0] for r in conn.execute(
            "SELECT t.id FROM threads t WHERE NOT EXISTS (SELECT 1 FROM messages m WHERE m.thread_id = t.id)")]
        conn.executemany("DELETE FROM messages WHERE thread_id = ?", [(t,) for t in test_threads])
        conn.executemany("DELETE FROM threads WHERE id = ?", [(t,) for t in test_threads + empty_threads])
        removed["test_threads"], removed["empty_threads"] = len(test_threads), len(empty_threads)
    except sqlite3.Error:
        pass
    return removed


def migrate_legacy_db(key: bytes, legacy: Optional[Path] = None, target: Optional[Path] = None) -> Dict:
    """Copy the old unencrypted database into a new encrypted one, verify it, and remove rows
    that old test runs created. The old file is left untouched."""
    import sqlcipher3.dbapi2 as sq

    legacy = Path(legacy or LEGACY_DB_PATH)
    target = Path(target or ENCRYPTED_DB_PATH)
    report: Dict = {"migrated": False}
    if target.exists():
        # An encrypted database without a keystore has lost its key (e.g. setup crashed after
        # migrating). Keep it aside instead of overwriting anything.
        aside = target.with_name(f"{target.name}.orphaned-{_stamp()}")
        os.replace(target, aside)
        report["orphaned_database_moved_to"] = aside.name
    if not legacy.exists():
        return report

    tmp = target.with_name(target.name + ".migrating")
    if tmp.exists():
        tmp.unlink()
    hexkey = bytes(key).hex()
    src = sq.connect(str(legacy))
    try:
        src.execute(f"ATTACH DATABASE ? AS enc KEY \"x'{hexkey}'\"", (str(tmp),))
        src.execute("SELECT sqlcipher_export('enc')")
        src.execute("DETACH DATABASE enc")
    finally:
        src.close()

    plain = sqlite3.connect(legacy.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        before = _table_counts(plain)
    finally:
        plain.close()
    dst = sq.connect(str(tmp))
    try:
        dst.execute(f"PRAGMA key = \"x'{hexkey}'\"")
        after = _table_counts(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if before != after or integrity != "ok":
            raise MigrationError(f"verification failed (integrity={integrity}, tables differ={before != after})")
        report["test_rows_removed"] = _remove_test_rows(dst)
        dst.commit()
    except Exception:
        dst.close()
        tmp.unlink(missing_ok=True)
        raise
    dst.close()
    os.replace(tmp, target)
    report.update({"migrated": True, "rows_copied": sum(before.values()), "tables": len(before),
                   "old_file_kept": legacy.name})
    return report


def legacy_db_present() -> bool:
    return LEGACY_DB_PATH.exists()


def delete_legacy_db() -> bool:
    """Deletes the old unencrypted database (and its -wal/-shm files) once the owner confirms."""
    if not is_open():
        raise DatabaseLocked("Unlock Sentinel first.")
    found = False
    for p in (LEGACY_DB_PATH, LEGACY_DB_PATH.with_name(LEGACY_DB_PATH.name + "-wal"),
              LEGACY_DB_PATH.with_name(LEGACY_DB_PATH.name + "-shm")):
        if p.exists():
            p.unlink()
            found = True
    return found
