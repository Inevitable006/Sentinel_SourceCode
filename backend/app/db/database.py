"""
Sentinel's database: SQLite encrypted with SQLCipher.

The database stays CLOSED while Sentinel is locked. The vault (app.core.vault) opens it with
the 32-byte data key after you unlock, and closes it when Sentinel locks. While it is closed,
SessionLocal() raises DatabaseLocked (the API turns that into HTTP 423), and an engine that was
closed refuses to reconnect, so a session created before the lock can't quietly reopen it.

On first setup, an old unencrypted database (jarvis_memory.db) is copied into the encrypted one
with SQLCipher's sqlcipher_export, verified table by table and (if you agree) cleaned of rows that
old test runs left behind. Research history from research_history.json is imported at unlock.
The old plaintext files are kept until you delete them from Settings; they are only deleted if
they are exactly the files that were imported (a SHA-256 fingerprint is kept in the database).
"""
import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import close_all_sessions, declarative_base, sessionmaker

from app.core.paths import SENTINEL_DATA_DIR

ENCRYPTED_DB_PATH = SENTINEL_DATA_DIR / "sentinel.db"            # SQLCipher, encrypted
LEGACY_DB_PATH = SENTINEL_DATA_DIR / "jarvis_memory.db"           # old unencrypted database
RESEARCH_JSON_PATH = SENTINEL_DATA_DIR / "research_history.json"  # old unencrypted research history

Base = declarative_base()


class DatabaseLocked(RuntimeError):
    """The encrypted database is closed because Sentinel is locked."""


class MigrationError(RuntimeError):
    pass


_state_lock = threading.RLock()
_engine = None
_opening = None             # engine being opened (allowed to connect before it is published)
_connections: set = set()   # every open DBAPI connection made with the key
_Session = sessionmaker(autocommit=False, autoflush=False)


def _url(path: Path, key: bytes) -> URL:
    # SQLCipher raw key syntax: pragma key = "x'<64 hex chars>'" (no password KDF; the key is
    # already random). The URL object masks the password in any repr or log line.
    return URL.create("sqlite+pysqlcipher", password=f"x'{key.hex()}'", database=str(path))


def open_database(key: bytes, path: Optional[Path] = None) -> None:
    """Open (or create) the encrypted database with the data key. Raises if the key is wrong."""
    global _engine, _opening
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise ValueError("the data key must be 32 bytes")
    with _state_lock:
        close_database()
        eng = create_engine(_url(Path(path or ENCRYPTED_DB_PATH), bytes(key)),
                            connect_args={"check_same_thread": False})

        @event.listens_for(eng, "do_connect")
        def _refuse_when_closed(dialect, conn_rec, cargs, cparams):
            # A closed (locked) engine must never open a new keyed connection.
            if _engine is not eng and _opening is not eng:
                raise DatabaseLocked("Sentinel is locked.")
            return None   # let SQLAlchemy connect normally

        @event.listens_for(eng, "connect")
        def _track(dbapi_conn, _record):
            _connections.add(dbapi_conn)

        @event.listens_for(eng, "close")
        def _untrack(dbapi_conn, _record):
            _connections.discard(dbapi_conn)

        @event.listens_for(eng, "close_detached")
        def _untrack_detached(dbapi_conn):
            _connections.discard(dbapi_conn)

        _opening = eng
        try:
            with eng.connect() as conn:            # SQLCipher only notices a wrong key on first read
                conn.execute(text("SELECT count(*) FROM sqlite_master"))
        except Exception:
            eng.dispose()
            raise
        finally:
            _opening = None
        _engine = eng
        _Session.configure(bind=eng)


def close_database() -> None:
    """Close the database: every session, every pooled and in-use connection. Nothing can keep
    reading or writing after Sentinel locks."""
    global _engine
    with _state_lock:
        eng, _engine = _engine, None             # from here on the engine refuses new connections
        try:
            close_all_sessions()
        except Exception:
            pass
        if eng is not None:
            eng.dispose()
        for conn in list(_connections):
            try:
                conn.close()
            except Exception:
                pass
        _connections.clear()
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


# Full-text index for personal memory (kept in sync by triggers) + a small metadata table.
_SCHEMA_SETUP = [
    "CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE IF NOT EXISTS secrets (name TEXT PRIMARY KEY, value TEXT NOT NULL, created_at TEXT, updated_at TEXT)",
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
_FTS_SETUP = _SCHEMA_SETUP   # old name, kept for compatibility


def init_db():
    """Create all tables plus the memory FTS index, triggers and metadata table. Idempotent."""
    from app.db import models  # noqa: F401  (registers the tables on Base.metadata)

    eng = get_engine()
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        for stmt in _SCHEMA_SETUP:
            conn.execute(text(stmt))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _meta_get(conn, key: str) -> Optional[str]:
    return conn.execute(text("SELECT value FROM app_meta WHERE key = :k"), {"k": key}).scalar()


def _meta_set(conn, key: str, value: str) -> None:
    conn.execute(text("INSERT OR REPLACE INTO app_meta (key, value) VALUES (:k, :v)"), {"k": key, "v": value})


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def open_for_vault(key: bytes, first_setup: bool = False, remove_test_rows: bool = True) -> Dict:
    """Called by the vault: on first setup, migrate the old database first; then open, create the
    schema and import old research history. Anything failing after the open closes it again."""
    report: Dict = {}
    if first_setup:
        report = migrate_legacy_db(key, remove_test_rows=remove_test_rows)
    open_database(key)
    try:
        init_db()
        imported = import_research_history_json()
        if imported:
            report["research_entries_imported"] = imported
        from app.core import retention, secrets_store
        removed = retention.apply_retention()
        if any(removed.values()):
            report["retention_removed"] = removed
        secrets_store.register_all_for_redaction()
    except Exception:
        close_database()
        raise
    return report


# ── one-time migration from the old unencrypted database ────────

# Rows that old test runs (before tests were isolated) wrote into the real database.
TEST_MEMORY_CONTENTS = (
    "I like pizza.",
    "My favorite color is neon green.",
    "My super secret password is password123.",
    "my favourite editor is neovim",
)


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
    except Exception:
        pass   # e.g. the old database has no memory table
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
    except Exception:
        pass
    return removed


def migrate_legacy_db(key: bytes, legacy: Optional[Path] = None, target: Optional[Path] = None,
                      remove_test_rows: bool = True) -> Dict:
    """Copy the old unencrypted database into a new encrypted one and verify it. Optionally remove
    rows that old test runs created. The old file is left untouched."""
    import sqlcipher3.dbapi2 as sq

    legacy = Path(legacy or LEGACY_DB_PATH)
    target = Path(target or ENCRYPTED_DB_PATH)
    if target.exists():
        raise MigrationError("An encrypted database already exists here; it will not be overwritten.")
    report: Dict = {"migrated": False}
    if not legacy.exists():
        return report

    tmp = target.with_name(target.name + ".migrating")
    for leftover in (tmp, tmp.with_name(tmp.name + "-journal")):
        if leftover.exists():
            leftover.unlink()
    raw_key = "x'" + bytes(key).hex() + "'"
    fingerprint = _sha256(legacy)
    src = sq.connect(str(legacy))
    try:
        src.execute("ATTACH DATABASE ? AS enc KEY ?", (str(tmp), raw_key))
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
        dst.execute(f"PRAGMA key = \"{raw_key}\"")
        after = _table_counts(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if before != after or integrity != "ok":
            raise MigrationError(f"verification failed (integrity={integrity}, tables differ={before != after})")
        report["test_rows_removed"] = _remove_test_rows(dst) if remove_test_rows else None
        dst.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
        dst.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES ('legacy_db_sha256', ?)", (fingerprint,))
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


def import_research_history_json(path: Optional[Path] = None) -> int:
    """Imports the old plaintext research_history.json (once per file version). Returns rows added."""
    p = Path(path or RESEARCH_JSON_PATH)
    if not p.exists():
        return 0
    fingerprint = _sha256(p)
    eng = get_engine()
    with eng.begin() as conn:
        if _meta_get(conn, "research_json_sha256") == fingerprint:
            return 0
        try:
            entries = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            entries = []
        existing = {(r[0], r[1], r[2]) for r in conn.execute(text("SELECT query, url, timestamp FROM research_history"))}
        added = 0
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict):
                continue
            row = (str(e.get("query", "")), str(e.get("url", "")), float(e.get("timestamp") or 0))
            if row in existing:
                continue
            conn.execute(text("INSERT INTO research_history (query, url, title, timestamp) VALUES (:q, :u, :t, :ts)"),
                         {"q": row[0], "u": row[1], "t": str(e.get("title", "")), "ts": row[2]})
            existing.add(row)
            added += 1
        _meta_set(conn, "research_json_sha256", fingerprint)
    return added


# ── old plaintext copies ────────────────────────────────────────

def _legacy_companions() -> List[Path]:
    return [LEGACY_DB_PATH.with_name(LEGACY_DB_PATH.name + s) for s in ("-wal", "-shm", "-journal")]


def old_plaintext_files() -> List[str]:
    """Names of old unencrypted files with personal data that are still on disk."""
    found = [LEGACY_DB_PATH] + _legacy_companions() + sorted(SENTINEL_DATA_DIR.glob("jarvis_memory.db.bak*")) \
        + [RESEARCH_JSON_PATH]
    return [p.name for p in found if p.exists()]


def legacy_db_present() -> bool:
    return bool(old_plaintext_files())


def delete_old_plaintext_files() -> Dict:
    """Deletes old unencrypted copies once the owner confirms. The old database and the research
    history file are deleted only if they are exactly what was imported; old .bak snapshots made by
    an earlier migration script are plaintext copies too and are always offered for deletion."""
    eng = get_engine()   # raises DatabaseLocked while locked
    with eng.connect() as conn:
        legacy_fp = _meta_get(conn, "legacy_db_sha256")
        research_fp = _meta_get(conn, "research_json_sha256")
    deleted, kept = [], []
    if LEGACY_DB_PATH.exists():
        if legacy_fp and _sha256(LEGACY_DB_PATH) == legacy_fp:
            for p in [LEGACY_DB_PATH] + _legacy_companions():
                if p.exists():
                    p.unlink()
                    deleted.append(p.name)
        else:
            kept.append({"file": LEGACY_DB_PATH.name, "why": "it is not the file that was moved into the encrypted database"})
    if RESEARCH_JSON_PATH.exists():
        if research_fp and _sha256(RESEARCH_JSON_PATH) == research_fp:
            RESEARCH_JSON_PATH.unlink()
            deleted.append(RESEARCH_JSON_PATH.name)
        else:
            kept.append({"file": RESEARCH_JSON_PATH.name, "why": "it changed after it was imported"})
    for p in sorted(SENTINEL_DATA_DIR.glob("jarvis_memory.db.bak*")):
        p.unlink()
        deleted.append(p.name)
    return {"deleted": deleted, "kept": kept}
