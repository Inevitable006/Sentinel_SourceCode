"""
Deletion and retention: what Sentinel keeps, for how long, and "forget" that really forgets.

- Forget all memories / delete all chats: rows are deleted with SQLite's secure_delete (freed space
  is overwritten), the memory search index follows through its triggers, and the database is
  vacuumed so nothing lingers in free pages.
- Retention (defaults: chats 180 days, research history 90 days; 0 = keep forever): applied when
  Sentinel unlocks and every few hours while it stays unlocked. Memories are kept until you forget
  them, except ones that were saved with an expiry date.
"""
import time
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import text

from app.db.database import get_engine

DEFAULTS = {"retention_chat_days": 180, "retention_research_days": 90}
MAX_DAYS = 3650


def _db_time(ts: float) -> str:
    """A UTC time in the text format SQLAlchemy uses for DateTime columns on SQLite."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def get_settings() -> Dict[str, int]:
    with get_engine().connect() as conn:
        rows = dict(conn.execute(text("SELECT key, value FROM app_meta WHERE key LIKE 'retention_%'")).fetchall())
    return {k: int(rows.get(k, v)) for k, v in DEFAULTS.items()}


def set_settings(chat_days: int, research_days: int) -> Dict[str, int]:
    for d in (chat_days, research_days):
        if not isinstance(d, int) or d < 0 or d > MAX_DAYS:
            raise ValueError(f"Choose 0 (keep forever) to {MAX_DAYS} days.")
    with get_engine().begin() as conn:
        for k, v in (("retention_chat_days", chat_days), ("retention_research_days", research_days)):
            conn.execute(text("INSERT OR REPLACE INTO app_meta (key, value) VALUES (:k, :v)"), {"k": k, "v": str(v)})
    return get_settings()


def _vacuum() -> None:
    with get_engine().connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").execute(text("VACUUM"))


def apply_retention(now: float = None) -> Dict[str, int]:
    """Deletes chats and research older than the retention periods, and memories past their expiry."""
    now = now if now is not None else time.time()
    s = get_settings()
    removed = {"chats": 0, "research": 0, "expired_memories": 0}
    with get_engine().begin() as conn:
        conn.execute(text("PRAGMA secure_delete = ON"))
        if s["retention_chat_days"]:
            cutoff = _db_time(now - s["retention_chat_days"] * 86400)
            ids = [r[0] for r in conn.execute(text("SELECT id FROM threads WHERE created_at < :c"), {"c": cutoff})]
            for tid in ids:
                conn.execute(text("DELETE FROM messages WHERE thread_id = :t"), {"t": tid})
                conn.execute(text("DELETE FROM threads WHERE id = :t"), {"t": tid})
            removed["chats"] = len(ids)
        if s["retention_research_days"]:
            removed["research"] = conn.execute(text("DELETE FROM research_history WHERE timestamp < :c"),
                                               {"c": now - s["retention_research_days"] * 86400}).rowcount
        removed["expired_memories"] = conn.execute(
            text("DELETE FROM memory_items WHERE expires_at IS NOT NULL AND expires_at < :n"),
            {"n": _db_time(now)}).rowcount
    return removed


def forget_all_memories() -> int:
    with get_engine().begin() as conn:
        conn.execute(text("PRAGMA secure_delete = ON"))
        n = conn.execute(text("DELETE FROM memory_items")).rowcount
        conn.execute(text("DELETE FROM fts_memory_items"))
    _vacuum()
    return n


def delete_all_chats() -> int:
    with get_engine().begin() as conn:
        conn.execute(text("PRAGMA secure_delete = ON"))
        n = conn.execute(text("SELECT count(*) FROM threads")).scalar()
        conn.execute(text("DELETE FROM messages"))
        conn.execute(text("DELETE FROM threads"))
    _vacuum()
    return int(n or 0)
