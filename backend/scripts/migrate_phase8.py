import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from app.db.database import engine, Base, SQLALCHEMY_DATABASE_URL
from app.db import models
from app.core.paths import SENTINEL_DATA_DIR

DB_PATH = SENTINEL_DATA_DIR / 'jarvis_memory.db'

def run_migration():
    print(f"Starting Phase 8 Database Migration...")
    print(f"Database path: {DB_PATH}")
    
    if not DB_PATH.exists():
        print("Error: Database not found! Sentinel must be run at least once before migrating.")
        return False
        
    # Check if migration already applied
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_items'")
    if cursor.fetchone():
        print("Migration already applied. memory_items table exists.")
        conn.close()
        return True
        
    # 1. Verification of existing data
    cursor.execute("SELECT count(*) FROM threads")
    thread_count = cursor.fetchone()[0]
    cursor.execute("SELECT count(*) FROM messages")
    message_count = cursor.fetchone()[0]
    print(f"Pre-migration data: {thread_count} threads, {message_count} messages.")
    conn.close()

    # 2. Create verified backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.with_suffix(f".db.bak.{timestamp}")
    print(f"Creating backup at {backup_path}...")
    shutil.copy2(DB_PATH, backup_path)
    
    if not backup_path.exists():
        print("CRITICAL ERROR: Failed to create backup. Aborting migration.")
        return False

    try:
        # 3. Apply schema
        print("Applying SQLAlchemy metadata...")
        Base.metadata.create_all(bind=engine)
        
        # 4. Apply FTS5 and Triggers
        print("Configuring FTS5 virtual table and synchronization triggers...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create FTS5 table
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_memory_items USING fts5(
                id UNINDEXED,
                content
            )
        """)
        
        # INSERT trigger
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items
            BEGIN
                INSERT INTO fts_memory_items(id, content) VALUES (new.id, new.content);
            END;
        """)
        
        # UPDATE trigger
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items
            BEGIN
                UPDATE fts_memory_items SET content = new.content WHERE id = old.id;
            END;
        """)
        
        # DELETE trigger
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items
            BEGIN
                DELETE FROM fts_memory_items WHERE id = old.id;
            END;
        """)
        
        conn.commit()
        
        # 5. Validation
        print("Running PRAGMA integrity_check...")
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()[0]
        if integrity_result != "ok":
            raise Exception(f"Integrity check failed: {integrity_result}")
            
        cursor.execute("SELECT count(*) FROM threads")
        new_thread_count = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM messages")
        new_message_count = cursor.fetchone()[0]
        
        if thread_count != new_thread_count or message_count != new_message_count:
            raise Exception(f"Data loss detected! Threads {thread_count}->{new_thread_count}, Messages {message_count}->{new_message_count}")
            
        print("Migration successful! Existing conversations preserved perfectly.")
        conn.close()
        return True
        
    except Exception as e:
        print(f"CRITICAL ERROR during migration: {e}")
        print("Rolling back to backup...")
        conn.close()
        shutil.copy2(backup_path, DB_PATH)
        
        # Verify rollback
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        print(f"Rollback integrity: {cursor.fetchone()[0]}")
        conn.close()
        return False

if __name__ == "__main__":
    run_migration()
