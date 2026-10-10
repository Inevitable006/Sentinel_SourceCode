"""Daily briefing: one local summary of what matters today. Read-only; it never acts.

Sections: reminders and drafts due, plans that need attention, portfolio change, PC health
(System Watch), backup age. Each section says plainly when it has nothing or no data.
"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.vault import vault
from app.db.database import SessionLocal
from app.db.models import PortfolioHistory, WorkItem

BACKUP_REMINDER_DAYS = 7


def _greeting(now: datetime) -> str:
    h = now.hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def _reminders(db, now_utc: datetime, now_local: datetime) -> dict:
    # "Today" ends at local midnight (due_at is stored in UTC).
    end_of_day = now_local.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(timezone.utc).isoformat()
    rows = (db.query(WorkItem).filter(WorkItem.kind.in_(["task", "calendar_draft"]),
                                      WorkItem.status.in_(["open", "due"]), WorkItem.due_at != None,
                                      WorkItem.due_at <= end_of_day)
            .order_by(WorkItem.due_at).limit(20).all())
    items = [{"title": r.title, "due_at": r.due_at, "overdue": r.due_at < now_utc.isoformat(), "kind": r.kind} for r in rows]
    open_tasks = db.query(WorkItem).filter(WorkItem.kind == "task", WorkItem.status.in_(["open", "due"])).count()
    return {"due_today": items, "open_tasks": open_tasks}


def _plans(db) -> list:
    rows = db.query(WorkItem).filter(WorkItem.kind == "plan", WorkItem.status.in_(["interrupted", "failed", "ready"])).limit(10).all()
    why = {"interrupted": "was interrupted; check before resuming", "failed": "an action failed",
           "ready": "is waiting for your approval of the next step"}
    return [{"title": r.title, "status": r.status, "note": why[r.status]} for r in rows]


def _portfolio(db) -> dict:
    rows = db.query(PortfolioHistory).order_by(PortfolioHistory.day.desc()).limit(2).all()
    if not rows:
        return {"available": False, "note": "No portfolio prices yet. Open Portfolio and press Refresh prices."}
    latest = rows[0]
    out = {"available": True, "day": latest.day, "value": round(latest.value, 2), "invested": round(latest.invested, 2),
           "gain": round(latest.value - latest.invested, 2)}
    if len(rows) > 1:
        prev = rows[1]
        change = latest.value - prev.value
        out.update(previous_day=prev.day, change=round(change, 2),
                   change_pct=round(change / prev.value * 100, 2) if prev.value else None)
    stale = (date.today() - date.fromisoformat(latest.day)).days
    if stale >= 1:
        out["note"] = f"Prices are from {latest.day}. Refresh in Portfolio for today's values."
    return out


def _health() -> dict:
    try:
        from app.core.system_watch import system_watch
        st = system_watch.status()
        return {"summary": st["summary"], "critical": sum(a["severity"] == "critical" for a in st["alerts"]),
                "alerts": len(st["alerts"]), "top": [a["title"] for a in st["alerts"][:3]]}
    except Exception as e:
        return {"summary": f"System Watch unavailable ({type(e).__name__}).", "critical": 0, "alerts": 0, "top": []}


def _backup(now: datetime) -> dict:
    from app.core import backup
    backups = backup.list_backups()
    if not backups:
        return {"last": None, "due": True, "note": "You have no backup yet. Settings → Backup → Create backup now."}
    last = datetime.fromisoformat(backups[0]["created"]).astimezone()
    days = (now - last).days
    return {"last": backups[0]["created"], "days": days, "due": days >= BACKUP_REMINDER_DAYS,
            "note": f"Last backup {days} day(s) ago." + (" Time for a new one." if days >= BACKUP_REMINDER_DAYS else "")}


def build_briefing(now: Optional[datetime] = None) -> dict:
    now = (now or datetime.now()).astimezone()      # local time with its offset
    now_utc = now.astimezone(timezone.utc)
    with SessionLocal() as db:
        reminders = _reminders(db, now_utc, now)
        plans = _plans(db)
        money = _portfolio(db)
    health, bk = _health(), _backup(now)
    return {"greeting": _greeting(now), "date": now.strftime("%A, %d %B %Y"), "reminders": reminders, "plans": plans,
            "portfolio": money, "health": health, "backup": bk, "spoken": spoken_text(reminders, plans, money, health, bk, now)}


def _inr(n: float) -> str:
    return f"{abs(n):,.0f} rupees"


def spoken_text(reminders, plans, money, health, bk, now) -> str:
    parts = [f"{_greeting(now)}. Here is your briefing for {now.strftime('%A, %d %B')}."]
    due = reminders["due_today"]
    if due:
        overdue = sum(r["overdue"] for r in due)
        parts.append(f"You have {len(due)} reminder{'s' if len(due) != 1 else ''} for today"
                     + (f", {overdue} already overdue" if overdue else "") + ": " + "; ".join(r["title"] for r in due[:3]) + ".")
    else:
        parts.append("No reminders are due today.")
    if plans:
        parts.append(f"{len(plans)} plan{'s' if len(plans) != 1 else ''} need{'s' if len(plans) == 1 else ''} your attention.")
    if money.get("available"):
        if "change" in money:
            word = "up" if money["change"] >= 0 else "down"
            parts.append(f"Your portfolio is {word} {_inr(money['change'])} since {money['previous_day']}, now worth {_inr(money['value'])}.")
        else:
            parts.append(f"Your portfolio is worth {_inr(money['value'])}.")
    parts.append(health["summary"])
    if bk.get("due"):
        parts.append("It's time to make a backup.")
    return " ".join(parts)


def create_briefing_router(verify_session_token):
    router = APIRouter(prefix="/api/briefing", dependencies=[Depends(verify_session_token)])

    def unlocked():
        if not vault.is_unlocked():
            raise HTTPException(423, "Unlock Sentinel first.")

    @router.get("")
    def get_briefing():
        unlocked()
        return build_briefing()

    @router.post("/read-aloud")
    def read_aloud():
        unlocked()
        from app.core.voice_service import voice_service
        voice_service.stop("briefing")
        voice_service.speak(build_briefing()["spoken"])
        return {"speaking": True}

    return router
