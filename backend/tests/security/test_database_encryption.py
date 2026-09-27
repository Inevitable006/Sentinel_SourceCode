"""
Encrypted database (Phase 1, step 1.4): the file is SQLCipher-encrypted, "locked" means closed
(even for connections already in use), and the one-time migration from the old unencrypted
database verifies itself, removes rows old test runs left behind, and leaves the old file alone.
"""
import os
import sqlite3

import pytest
from sqlalchemy import text

from app.db import database as dbm


def test_database_file_is_encrypted():
    assert not dbm.ENCRYPTED_DB_PATH.read_bytes().startswith(b"SQLite format 3")


def test_plain_sqlite_cannot_read_it():
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(dbm.ENCRYPTED_DB_PATH).execute("SELECT * FROM memory_items").fetchall()


def test_memory_text_never_appears_on_disk():
    from app.core.memory_service import memory_service
    db = dbm.SessionLocal()
    try:
        assert memory_service.remember(db, "I water the zebra plant every Tuesday")
    finally:
        db.close()
    assert b"zebra" not in dbm.ENCRYPTED_DB_PATH.read_bytes()


def test_locked_database_refuses_access(locked_db):
    assert not dbm.is_open()
    with pytest.raises(dbm.DatabaseLocked):
        dbm.SessionLocal()
    with pytest.raises(dbm.DatabaseLocked):
        dbm.get_engine()


def test_locking_cuts_off_connections_already_in_use(reopen_db):
    s = dbm.SessionLocal()
    s.execute(text("SELECT count(*) FROM memory_items")).scalar()   # connection now checked out
    dbm.close_database()
    with pytest.raises(Exception):
        s.execute(text("SELECT count(*) FROM memory_items")).scalar()
    try:
        s.close()
    except Exception:
        pass


def test_wrong_key_is_rejected(reopen_db):
    dbm.close_database()
    with pytest.raises(Exception):
        dbm.open_database(os.urandom(32))
    assert not dbm.is_open()


def _old_style_database(tmp_path):
    """An old unencrypted jarvis_memory.db with real rows plus rows old test runs left behind."""
    p = tmp_path / "jarvis_memory.db"
    c = sqlite3.connect(p)
    c.executescript("""
        CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, created_at DATETIME);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, thread_id TEXT, role TEXT, content TEXT);
        CREATE TABLE memory_items (id TEXT PRIMARY KEY, content TEXT NOT NULL, category TEXT, source TEXT,
            provenance TEXT, confidence INTEGER, importance INTEGER, created_at DATETIME,
            last_accessed_at DATETIME, expires_at DATETIME);
        CREATE VIRTUAL TABLE fts_memory_items USING fts5(id UNINDEXED, content);
        CREATE TRIGGER memory_items_ad AFTER DELETE ON memory_items
        BEGIN DELETE FROM fts_memory_items WHERE id = old.id; END;
    """)
    rows = [("m1", "My sister's birthday is 14 March"), ("m2", "I like pizza."), ("m3", "my favourite editor is neovim")]
    c.executemany("INSERT INTO memory_items (id, content, confidence, importance) VALUES (?, ?, 100, 3)", rows)
    c.executemany("INSERT INTO fts_memory_items (id, content) VALUES (?, ?)", rows)
    c.executemany("INSERT INTO threads (id, title) VALUES (?, ?)",
                  [("t-real", "Plans"), ("t-test", "New Chat"), ("t-empty", "Websocket Session")])
    c.executemany("INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)",
                  [("t-real", "user", "What is Python?"), ("t-real", "assistant", "A language."),
                   ("t-test", "user", "What is Python?")])
    c.commit()
    c.close()
    return p


def test_migration_encrypts_verifies_and_cleans(tmp_path):
    import sqlcipher3.dbapi2 as sq
    legacy, target, key = _old_style_database(tmp_path), tmp_path / "sentinel.db", os.urandom(32)
    before = legacy.read_bytes()
    report = dbm.migrate_legacy_db(key, legacy=legacy, target=target)
    assert report["migrated"] is True and report["old_file_kept"] == "jarvis_memory.db"
    assert report["test_rows_removed"] == {"test_memories": 2, "test_threads": 1, "empty_threads": 1}
    assert legacy.read_bytes() == before                           # the old file is untouched
    raw = target.read_bytes()
    assert b"birthday" not in raw and not raw.startswith(b"SQLite format 3")
    c = sq.connect(str(target))
    c.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    assert [r[0] for r in c.execute("SELECT id FROM memory_items ORDER BY id")] == ["m1"]
    assert [r[0] for r in c.execute("SELECT id FROM fts_memory_items")] == ["m1"]    # index kept in step
    assert [r[0] for r in c.execute("SELECT id FROM threads ORDER BY id")] == ["t-real"]
    assert c.execute("SELECT count(*) FROM messages").fetchone()[0] == 2
    c.close()
    assert not (tmp_path / "sentinel.db.migrating").exists()


def test_migration_with_no_old_database(tmp_path):
    report = dbm.migrate_legacy_db(os.urandom(32), legacy=tmp_path / "none.db", target=tmp_path / "s.db")
    assert report == {"migrated": False}


def test_orphaned_encrypted_database_is_kept_aside(tmp_path):
    target = tmp_path / "sentinel.db"
    target.write_bytes(b"an encrypted database whose key was lost")
    report = dbm.migrate_legacy_db(os.urandom(32), legacy=tmp_path / "none.db", target=target)
    moved = report["orphaned_database_moved_to"]
    assert moved.startswith("sentinel.db.orphaned-") and (tmp_path / moved).exists() and not target.exists()
