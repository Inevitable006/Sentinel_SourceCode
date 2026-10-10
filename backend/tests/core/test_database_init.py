"""Database bootstrap: a fresh install must get the FTS5 memory index."""
from sqlalchemy import text

from app.db.database import get_engine, init_db


def _names(kind):
    with get_engine().connect() as c:
        return {r[0] for r in c.execute(text("SELECT name FROM sqlite_master WHERE type = :k"), {"k": kind})}


def test_init_db_creates_fts_index_and_triggers():
    init_db()
    assert "fts_memory_items" in _names("table")
    assert {"memory_items_ai", "memory_items_au", "memory_items_ad"} <= _names("trigger")


def test_init_db_is_idempotent():
    init_db()
    init_db()


def test_init_db_backfills_memories_missing_from_the_index():
    init_db()
    with get_engine().begin() as c:
        c.execute(text("INSERT INTO memory_items (id, content, confidence, importance) "
                       "VALUES ('bf-1', 'likes green tea', 100, 3)"))
        # Simulate a database whose memories were written before the index existed.
        c.execute(text("DELETE FROM fts_memory_items WHERE id = 'bf-1'"))
    init_db()
    with get_engine().connect() as c:
        hits = [r[0] for r in c.execute(text("SELECT id FROM fts_memory_items WHERE fts_memory_items MATCH 'green'"))]
    assert "bf-1" in hits


def test_remember_works_on_a_fresh_install():
    from app.core.memory_service import memory_service
    from app.db.database import SessionLocal

    init_db()
    db = SessionLocal()
    try:
        assert memory_service.remember(db, "my favourite editor is neovim")
    finally:
        db.close()
