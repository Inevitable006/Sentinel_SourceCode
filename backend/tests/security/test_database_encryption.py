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
    fingerprint = c.execute("SELECT value FROM app_meta WHERE key = 'legacy_db_sha256'").fetchone()[0]
    c.close()
    assert fingerprint == dbm._sha256(legacy)                       # remembered for the safe delete later
    assert not (tmp_path / "sentinel.db.migrating").exists()


def test_migration_can_keep_old_test_rows(tmp_path):
    import sqlcipher3.dbapi2 as sq
    legacy, target, key = _old_style_database(tmp_path), tmp_path / "sentinel.db", os.urandom(32)
    report = dbm.migrate_legacy_db(key, legacy=legacy, target=target, remove_test_rows=False)
    assert report["test_rows_removed"] is None
    c = sq.connect(str(target))
    c.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    assert c.execute("SELECT count(*) FROM memory_items").fetchone()[0] == 3
    c.close()


def test_migration_with_no_old_database(tmp_path):
    report = dbm.migrate_legacy_db(os.urandom(32), legacy=tmp_path / "none.db", target=tmp_path / "s.db")
    assert report == {"migrated": False}


def test_migration_never_overwrites_an_existing_encrypted_database(tmp_path):
    target = tmp_path / "sentinel.db"
    target.write_bytes(b"an encrypted database whose keystore went missing")
    with pytest.raises(dbm.MigrationError):
        dbm.migrate_legacy_db(os.urandom(32), legacy=_old_style_database(tmp_path), target=target)
    assert target.read_bytes() == b"an encrypted database whose keystore went missing"


# ── review finding 2a: a session made before the lock can't reopen the database ──

def test_a_session_from_before_the_lock_cannot_reconnect(reopen_db):
    s = dbm.SessionLocal()
    s.execute(text("SELECT count(*) FROM memory_items")).scalar()
    s.commit()                                                     # connection goes back to the pool
    dbm.close_database()
    with pytest.raises(Exception):
        s.execute(text("INSERT INTO app_meta (key, value) VALUES ('after-lock', 'x')"))
        s.commit()
    try:
        s.close()
    except Exception:
        pass
    assert not dbm._connections                                   # no keyed connection left open


# ── research history is imported, then its plaintext file can be deleted safely ──

def test_research_history_json_is_imported_once(tmp_path):
    import json as _json
    p = tmp_path / "research_history.json"
    p.write_text(_json.dumps([{"query": "q1", "url": "https://a.example", "title": "A", "timestamp": 1.0},
                              {"query": "q2", "url": "https://b.example", "title": "B", "timestamp": 2.0}]))
    assert dbm.import_research_history_json(p) == 2
    assert dbm.import_research_history_json(p) == 0               # same file: nothing new
    from app.core.research_service import research_service
    queries = {h["query"] for h in research_service.get_history()}
    assert {"q1", "q2"} <= queries


def test_old_plaintext_files_are_deleted_only_when_they_match(monkeypatch, tmp_path):
    legacy = tmp_path / "jarvis_memory.db"
    legacy.write_bytes(b"old plaintext database")
    bak = tmp_path / "jarvis_memory.db.bak.20260801"
    bak.write_bytes(b"older snapshot")
    monkeypatch.setattr(dbm, "LEGACY_DB_PATH", legacy)
    monkeypatch.setattr(dbm, "RESEARCH_JSON_PATH", tmp_path / "research_history.json")
    monkeypatch.setattr(dbm, "SENTINEL_DATA_DIR", tmp_path)
    assert set(dbm.old_plaintext_files()) == {"jarvis_memory.db", "jarvis_memory.db.bak.20260801"}
    with dbm.get_engine().begin() as c:
        dbm._meta_set(c, "legacy_db_sha256", "not-the-same-file")
    out = dbm.delete_old_plaintext_files()
    assert legacy.exists() and out["kept"][0]["file"] == "jarvis_memory.db"   # never migrated this exact file
    assert out["deleted"] == ["jarvis_memory.db.bak.20260801"] and not bak.exists()
    with dbm.get_engine().begin() as c:
        dbm._meta_set(c, "legacy_db_sha256", dbm._sha256(legacy))
    assert dbm.delete_old_plaintext_files()["deleted"] == ["jarvis_memory.db"] and not legacy.exists()


def test_deleting_old_files_needs_an_unlocked_database(locked_db):
    with pytest.raises(dbm.DatabaseLocked):
        dbm.delete_old_plaintext_files()
