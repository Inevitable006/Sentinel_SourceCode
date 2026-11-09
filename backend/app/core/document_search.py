"""Bounded keyword retrieval inside the existing encrypted database."""
import re
from sqlalchemy import text

# Triggers make all existing document creation/edit/deletion paths transactional.
SCHEMA = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_documents USING fts5(id UNINDEXED, title, content, tokenize='unicode61')",
    """CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON work_items
       WHEN new.kind = 'document' BEGIN
       INSERT INTO fts_documents(id,title,content) VALUES(new.id,new.title,new.content); END""",
    """CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE OF kind,title,content ON work_items
       WHEN old.kind='document' OR new.kind='document' BEGIN
       DELETE FROM fts_documents WHERE id=old.id;
       INSERT INTO fts_documents(id,title,content)
       SELECT new.id,new.title,new.content WHERE new.kind='document'; END""",
    """CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON work_items
       WHEN old.kind='document' BEGIN
       DELETE FROM fts_documents WHERE id=old.id; END""",
    """INSERT INTO fts_documents(id,title,content)
       SELECT id,title,content FROM work_items WHERE kind='document'
       AND id NOT IN (SELECT id FROM fts_documents)""",
]


def search_documents(db, query: str, limit: int = 5):
    """Literal words joined by AND; FTS operators are never user-controlled."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300:
        raise ValueError("Enter 1 to 300 characters to search.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("Choose between 1 and 20 results.")
    words = list(dict.fromkeys(re.findall(r"[^\W_]+", query, flags=re.UNICODE)))
    if not words:
        return []
    if len(words) > 20:
        raise ValueError("Use no more than 20 search words.")
    match = " AND ".join('"' + word + '"' for word in words)
    rows = db.execute(text("""
        SELECT w.id,w.title,
               snippet(fts_documents,2,'','',' … ',48) AS excerpt
        FROM fts_documents JOIN work_items w ON w.id=fts_documents.id
        WHERE fts_documents MATCH :match AND w.kind='document'
        ORDER BY bm25(fts_documents,0,5,1), w.id
        LIMIT :limit
    """), {"match": match, "limit": limit}).mappings()
    return [{"id": row["id"], "title": row["title"], "excerpt": row["excerpt"][:1200]}
            for row in rows]
