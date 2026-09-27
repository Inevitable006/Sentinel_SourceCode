from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.paths import SENTINEL_DATA_DIR

# DB file will be saved securely in AppData/Roaming/sentinel/
SQLALCHEMY_DATABASE_URL = f"sqlite:///{SENTINEL_DATA_DIR / 'jarvis_memory.db'}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Full-text index for personal memory, kept in sync by triggers.
# (Previously only created by scripts/migrate_phase8.py, so a fresh install
# crashed on the first "remember that ..." or memory lookup.)
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

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for stmt in _FTS_SETUP:
            conn.execute(text(stmt))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
