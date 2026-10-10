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


class Holding(Base):
    """Portfolio Advisor: one investment the owner holds (entered or imported; never from a bank login)."""
    __tablename__ = "portfolio_holdings"
    id = Column(String, primary_key=True)
    kind = Column(String, index=True, nullable=False)    # "mf" | "stock" | "other"
    name = Column(Text, nullable=False)
    symbol = Column(String, default="")                  # NSE symbol, or AMFI scheme code for funds
    isin = Column(String, default="")
    units = Column(Float, default=0.0)
    avg_cost = Column(Float, default=0.0)                # per unit
    buy_date = Column(String, nullable=True)             # ISO date, optional
    last_price = Column(Float, nullable=True)
    price_date = Column(String, nullable=True)
    price_source = Column(String, nullable=True)
    category = Column(String, default="")                # e.g. equity / debt / hybrid / gold
    created_at = Column(DateTime, default=datetime.utcnow)


class FileAction(Base):
    """A file change Sentinel made with approval, and how to undo it while the window is open."""
    __tablename__ = "file_actions"
    id = Column(String, primary_key=True)
    op = Column(String, nullable=False)             # write | move | delete | mkdir
    path = Column(Text, nullable=False)             # relative to the approved folder
    dest = Column(Text, nullable=True)              # for move
    snapshot = Column(Text, nullable=True)          # undo copy (file name in the undo store), if any
    existed = Column(Integer, default=0)            # did the target exist before (write)?
    summary = Column(Text, default="")
    created = Column(Float, nullable=False)         # epoch seconds
    undo_until = Column(Float, nullable=False)
    status = Column(String, default="done")         # done | undone | final


class HoldingCost(Base):
    """Portfolio Advisor: a fund's yearly expense ratio (TER), entered by the owner from the factsheet/app."""
    __tablename__ = "portfolio_costs"
    holding_id = Column(String, primary_key=True)
    ter_pct = Column(Float, nullable=False)
    checked_on = Column(String, nullable=True)     # when the owner last checked it


class PortfolioTransaction(Base):
    """Portfolio Advisor: one buy / sell / dividend, used for the true yearly return (XIRR)."""
    __tablename__ = "portfolio_transactions"
    id = Column(String, primary_key=True)
    holding_id = Column(String, index=True, nullable=False)
    day = Column(String, nullable=False)          # ISO date
    kind = Column(String, nullable=False)         # buy | sell | dividend
    units = Column(Float, default=0.0)
    amount = Column(Float, nullable=False)        # rupees paid (buy) or received (sell/dividend), always positive


class PortfolioHistory(Base):
    """Portfolio Advisor: total value once per day (recorded when prices are refreshed)."""
    __tablename__ = "portfolio_history"
    day = Column(String, primary_key=True)        # ISO date
    value = Column(Float, nullable=False)
    invested = Column(Float, nullable=False)


class InvestorProfile(Base):
    """Portfolio Advisor: the owner's goals and comfort with risk (single row, id=1)."""
    __tablename__ = "investor_profile"
    id = Column(Integer, primary_key=True)
    data = Column(Text, default="{}")


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
