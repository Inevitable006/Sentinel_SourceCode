from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Thread(Base):
    __tablename__ = "threads"
    
    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan", order_by="Message.id")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, ForeignKey("threads.id"))
    role = Column(String, index=True) # 'user' or 'assistant'
    content = Column(Text)
    thread = relationship("Thread", back_populates="messages")

class AppSettings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    system_prompt = Column(Text, default="You are Sentinel, a highly advanced, concise, and helpful personal AI assistant.")

class MemoryItem(Base):
    __tablename__ = "memory_items"
    
    id = Column(String, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    category = Column(String, index=True) # e.g., 'preference', 'fact', 'project'
    source = Column(String)               # e.g., 'user_statement'
    provenance = Column(Text)             # JSON metadata about source
    confidence = Column(Integer, default=100) # 0-100 score
    importance = Column(Integer, default=3)   # 1-5
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)



class ResearchEntry(Base):
    """One web-search result Sentinel showed you (was research_history.json, unencrypted)."""
    __tablename__ = "research_history"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(Text)
    url = Column(Text)
    title = Column(Text)
    timestamp = Column(Float, index=True)


class WatchBaseline(Base):
    """System Watch: what the owner accepted as normal on this PC (one row per item)."""
    __tablename__ = "watch_baseline"
    id = Column(String, primary_key=True)          # "<category>:<key>"
    category = Column(String, index=True, nullable=False)
    key = Column(Text, nullable=False)
    detail = Column(Text, default="")
    accepted_at = Column(DateTime, default=datetime.utcnow)


class WatchAlert(Base):
    """System Watch: something that looked off, with the steps shown to the owner."""
    __tablename__ = "watch_alerts"
    id = Column(String, primary_key=True)          # "<category>:<key>" so a repeat updates, not duplicates
    category = Column(String, index=True, nullable=False)
    key = Column(Text, nullable=False)
    severity = Column(String, default="warning")   # info | warning | critical
    title = Column(Text, nullable=False)
    detail = Column(Text, default="")
    steps = Column(Text, default="[]")             # JSON list of plain-language steps
    status = Column(String, index=True, default="open")   # open | accepted | resolved
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)


class WorkItem(Base):
    """Owner-created tasks, drafts and plans, inside the encrypted database."""
    __tablename__ = "work_items"
    id = Column(String, primary_key=True)
    kind = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, default="")
    status = Column(String, default="open")
    due_at = Column(String, nullable=True)
    payload = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
