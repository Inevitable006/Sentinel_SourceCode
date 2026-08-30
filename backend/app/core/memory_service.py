from sqlalchemy.orm import Session
from app.db import models
import uuid
from typing import List, Dict

class MemoryService:
    def create_thread(self, db: Session, title: str = "New Chat") -> str:
        """Creates a new conversation thread and returns its ID."""
        thread_id = str(uuid.uuid4())
        thread = models.Thread(id=thread_id, title=title)
        db.add(thread)
        db.commit()
        return thread_id
        
    def add_message(self, db: Session, thread_id: str, role: str, content: str):
        """Adds a message to the database."""
        # Ensure thread exists
        thread = db.query(models.Thread).filter(models.Thread.id == thread_id).first()
        if not thread:
            thread = models.Thread(id=thread_id, title="New Chat")
            db.add(thread)
            
        message = models.Message(thread_id=thread_id, role=role, content=content)
        db.add(message)
        db.commit()
        
    def get_context_history(self, db: Session, thread_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """Retrieves the last N messages for a thread to build context."""
        messages = db.query(models.Message).filter(models.Message.thread_id == thread_id).order_by(models.Message.id.desc()).limit(limit).all()
        # Reverse to chronological order
        messages.reverse()
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    # --- PHASE 8: PERSISTENT MEMORY ---

    def _is_sensitive(self, content: str) -> bool:
        """Memory Policy: Reject sensitive credentials."""
        sensitive_keywords = ["password", "api_key", "secret", "token", "private_key", "credential"]
        lower_content = content.lower()
        for kw in sensitive_keywords:
            if kw in lower_content:
                return True
        return False

    def remember(self, db: Session, content: str, category: str = "fact", source: str = "user_statement") -> bool:
        """Explicit memory creation with duplication handling and policy checks."""
        # 1. Memory Policy Gate
        if self._is_sensitive(content):
            print("Memory Policy Violation: Sensitive data rejected.")
            return False
            
        content = content.strip()
        
        # 2. Duplicate Detection via FTS5
        from sqlalchemy import text
        # Escape quotes for FTS
        safe_content = content.replace("'", "''").replace('"', '""')
        # We query the FTS table for exactly this phrasing or high similarity
        query = text(f"""
            SELECT id FROM fts_memory_items 
            WHERE fts_memory_items MATCH '"{safe_content}"'
        """)
        existing = db.execute(query).first()
        
        from datetime import datetime
        if existing:
            # UPDATE
            mem_id = existing[0]
            memory = db.query(models.MemoryItem).filter(models.MemoryItem.id == mem_id).first()
            if memory:
                memory.last_accessed_at = datetime.utcnow()
                memory.confidence = min(memory.confidence + 10, 100) # Boost confidence
                db.commit()
                print(f"Memory updated: {mem_id}")
                return True
                
        # CREATE
        mem_id = str(uuid.uuid4())
        new_memory = models.MemoryItem(
            id=mem_id,
            content=content,
            category=category,
            source=source
        )
        db.add(new_memory)
        db.commit()
        print(f"Memory created: {mem_id}")
        return True

    def retrieve_relevant_memory(self, db: Session, query_str: str, limit: int = 3) -> List[str]:
        """Bounded FTS5 Retrieval."""
        if not query_str or len(query_str) < 3:
            return []
            
        from sqlalchemy import text
        import re
        
        # Clean query for FTS5 (remove special characters that break MATCH)
        safe_query = re.sub(r'[^a-zA-Z0-9\s]', '', query_str).strip()
        if not safe_query:
            return []
            
        # Convert "Hello world" to "Hello OR world" for broader keyword match
        fts_query = " OR ".join(safe_query.split())
        
        # Retrieve by BM25 rank, combined with importance
        query = text(f"""
            SELECT m.content 
            FROM fts_memory_items f
            JOIN memory_items m ON f.id = m.id
            WHERE f.fts_memory_items MATCH :fts
            ORDER BY bm25(fts_memory_items), m.importance DESC, m.last_accessed_at DESC
            LIMIT :limit
        """)
        
        results = db.execute(query, {"fts": fts_query, "limit": limit}).fetchall()
        
        # Update last_accessed_at for retrieved memories
        # (Omitted here to keep reads perfectly lightweight, could be done via background queue)
        
        return [row[0] for row in results]

    def forget(self, db: Session, content_match: str) -> bool:
        """Deletes a memory matching the string."""
        from sqlalchemy import text
        safe_content = content_match.replace("'", "''").replace('"', '""')
        query = text(f"""
            SELECT id FROM fts_memory_items 
            WHERE fts_memory_items MATCH '"{safe_content}"'
        """)
        existing = db.execute(query).fetchall()
        deleted = False
        for row in existing:
            mem_id = row[0]
            db.query(models.MemoryItem).filter(models.MemoryItem.id == mem_id).delete()
            deleted = True
            
        db.commit()
        return deleted

memory_service = MemoryService()
