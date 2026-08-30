from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
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

