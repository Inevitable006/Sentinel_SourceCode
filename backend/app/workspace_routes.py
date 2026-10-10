"""Local productivity and privacy. Nothing in this router sends mail or auto-executes tools."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import threading
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.db.database import SessionLocal
from app.db.models import WorkItem, MemoryItem, Thread, Message, ResearchEntry
from app.core.vault import vault

Kind = Literal["task", "plan", "email_draft", "calendar_draft", "document"]
work_lock = threading.Lock()


class Step(BaseModel):
    tool: str = Field(min_length=1, max_length=100)
    args: dict = Field(default_factory=dict)


class ItemBody(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(default="", max_length=60000)
    due_at: str | None = None
    steps: list[Step] = Field(default_factory=list, max_length=20)

    @field_validator("due_at")
    @classmethod
    def due(cls, value):
        if value:
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    raise ValueError()
                return dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                raise ValueError("Choose a date and time with a timezone.")
        return None


class ConfirmBody(BaseModel):
    pin: str | None = None
    token: str = ""
    revision: str = ""


class StateBody(BaseModel):
    status: Literal["open", "done", "cancelled"]


class MemoryBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class SkillBody(BaseModel):
    enabled: bool
    pin: str | None = None


def view(item):
    payload = json.loads(item.payload or "{}")
    revision = hashlib.sha256((item.id + item.payload + item.status).encode()).hexdigest()
    return {"id": item.id, "kind": item.kind, "title": item.title, "content": item.content,
            "status": item.status, "due_at": item.due_at, "payload": payload, "revision": revision}


def require_owner():
    if not vault.is_unlocked():
        raise HTTPException(423, "Unlock Sentinel first.")


def skill_enabled(name):
    """Skill switches live in the encrypted database. While it is closed (locked) no chat,
    plan or tool route can run at all, so there is nothing to switch; otherwise fail closed."""
    from app.db import database as db_store
    if not db_store.is_open():
        return True
    try:
        with SessionLocal() as db:
            setting = db.get(WorkItem, "skill:" + name)
            return setting is None or setting.status != "disabled"
    except Exception:
        return False


def recover_interrupted():
    """A plan left "running" with no action actually running was interrupted (lock, crash,
    restart). Mark it for review; it is never re-run automatically."""
    if not work_lock.acquire(blocking=False):
        return 0  # an action is running right now; its row is not stale
    try:
        with SessionLocal() as db:
            count = db.query(WorkItem).filter(WorkItem.status == "running").update(
                {WorkItem.status: "interrupted"}, synchronize_session=False)
            db.commit()
            return count
    finally:
        work_lock.release()


def due_reminders():
    """Only changes reminder state; never runs actions in the background."""
    with SessionLocal() as db:
        now = datetime.now(timezone.utc).isoformat()
        db.query(WorkItem).filter(WorkItem.kind.in_(["task", "calendar_draft"]),
            WorkItem.status == "open", WorkItem.due_at != None, WorkItem.due_at <= now).update(
                {WorkItem.status: "due"}, synchronize_session=False)
        db.commit()


def create_workspace_router(verify_session_token, require_pin):
    router = APIRouter(prefix="/api/workspace", dependencies=[Depends(verify_session_token), Depends(require_owner)])

    @router.get("/items/{kind}")
    def items(kind: Kind):
        due_reminders()
        recover_interrupted()
        with SessionLocal() as db:
            return [view(row) for row in db.query(WorkItem).filter_by(kind=kind).order_by(WorkItem.created_at.desc()).limit(200)]

    @router.post("/items/{kind}")
    def create(kind: Kind, body: ItemBody):
        from app.core.policy_engine import policy_engine, PolicyDecision
        if kind == "plan":
            if not body.steps:
                raise HTTPException(400, "Add at least one action to the plan.")
            for step in body.steps:
                decision, reason = policy_engine.evaluate(step.tool, step.args, "plan-preview")
                if decision == PolicyDecision.DENY:
                    raise HTTPException(400, reason)
        payload = {"steps": [step.model_dump() for step in body.steps], "next": 0, "results": []}
        with SessionLocal() as db:
            item = WorkItem(id=str(uuid.uuid4()), kind=kind, title=body.title.strip(), content=body.content,
                            due_at=body.due_at, status="open", payload=json.dumps(payload))
            db.add(item); db.commit()
            return view(item)

    @router.post("/items/{item_id}/update")
    def update(item_id: str, body: ItemBody):
        from app.core.policy_engine import policy_engine, PolicyDecision
        with SessionLocal() as db:
            item = db.get(WorkItem, item_id)
            if item is None or item.kind == "skill_setting":
                raise HTTPException(404, "Item not found.")
            if item.status == "running":
                raise HTTPException(409, "Wait for the current action to finish.")
            payload = json.loads(item.payload or "{}")
            if item.kind == "plan":
                if payload.get("next", 0) > 0 or payload.get("results"):
                    raise HTTPException(409, "A plan cannot be edited after an action has run. Create a new plan.")
                if not body.steps:
                    raise HTTPException(400, "Add at least one action to the plan.")
                for step in body.steps:
                    decision, reason = policy_engine.evaluate(step.tool, step.args, "plan-preview")
                    if decision == PolicyDecision.DENY:
                        raise HTTPException(400, reason)
                payload = {"steps": [step.model_dump() for step in body.steps], "next": 0, "results": []}
            item.title = body.title.strip(); item.content = body.content; item.due_at = body.due_at
            if item.status == "due" and body.due_at and body.due_at > datetime.now(timezone.utc).isoformat():
                item.status = "open"
            item.payload = json.dumps(payload); db.commit()
            return view(item)

    @router.post("/items/{item_id}/state")
    def state(item_id: str, body: StateBody):
        with SessionLocal() as db:
            item = db.get(WorkItem, item_id)
            if item is None or item.kind == "skill_setting":
                raise HTTPException(404, "Item not found.")
            if item.status == "running":
                raise HTTPException(409, "Wait for the current action to finish or use Emergency stop.")
            if item.kind == "plan" and body.status != "cancelled":
                # After an interruption the owner reviews the results, then explicitly resumes.
                if body.status == "open" and item.status == "interrupted":
                    item.status = "ready"; db.commit()
                    return view(item)
                raise HTTPException(400, "Plan progress is tracked by completed actions.")
            item.status = body.status; db.commit()
            return view(item)

    @router.post("/items/{item_id}/delete")
    def delete(item_id: str, body: ConfirmBody):
        require_pin(body.pin, "Enter your PIN to delete this item.")
        with SessionLocal() as db:
            item = db.get(WorkItem, item_id)
            if item is None or item.kind == "skill_setting":
                raise HTTPException(404, "Item not found.")
            if item.status == "running":
                raise HTTPException(409, "This action is still running.")
            db.delete(item); db.commit()
        return {"deleted": True}

    @router.get("/tools")
    def tools():
        from app.core.tool_registry import tool_registry
        return [tool.tool_schema.model_dump() for tool in tool_registry.tools.values()
                if int(tool.tool_schema.risk_tier) < 4 and not tool.tool_schema.name.startswith("test_")]

    @router.post("/plans/{item_id}/prepare")
    def prepare(item_id: str):
        from app.core.token_service import token_service
        from app.core.tool_registry import tool_registry
        from app.core.policy_engine import policy_engine, PolicyDecision
        with SessionLocal() as db:
            item = db.get(WorkItem, item_id)
            if not item or item.kind != "plan" or item.status not in ("open", "ready"):
                raise HTTPException(409, "This plan is not ready to run. Review an interrupted or failed plan first.")
            data = view(item); payload = data["payload"]
            if payload["next"] >= len(payload["steps"]):
                raise HTTPException(409, "This plan is complete.")
            step = payload["steps"][payload["next"]]
            decision, reason = policy_engine.evaluate(step["tool"], step["args"], item.id)
            if decision == PolicyDecision.DENY:
                raise HTTPException(403, reason)
            tier = int(tool_registry.get_tool(step["tool"]).tool_schema.risk_tier)
            token = token_service.generate_token(item.id, step["tool"], step["args"], tier)
            return {"step": step, "risk": tier, "token": token, "revision": data["revision"]}

    @router.post("/plans/{item_id}/run")
    async def run(item_id: str, body: ConfirmBody):
        from app.core.secure_runner import secure_runner
        from app.core.tool_registry import tool_registry
        if not work_lock.acquire(blocking=False):
            raise HTTPException(409, "Another plan action is running.")
        try:
            with SessionLocal() as db:
                item = db.get(WorkItem, item_id)
                if not item or item.kind != "plan" or item.status not in ("open", "ready"):
                    raise HTTPException(409, "This plan is not ready to run.")
                data = view(item)
                if data["revision"] != body.revision or not body.token:
                    raise HTTPException(409, "Review the current plan action before approving.")
                payload = data["payload"]; step = payload["steps"][payload["next"]]
                tool = tool_registry.get_tool(step["tool"])
                if tool is None:
                    raise HTTPException(400, "This tool is no longer available.")
                if int(tool.tool_schema.risk_tier) >= 3:
                    require_pin(body.pin, "Enter your PIN to run this action.")
                item.status = "running"; db.commit()
            try:
                result = await asyncio.to_thread(secure_runner.execute, step["tool"], step["args"], item_id,
                                                 item_id, body.token, True)
                require_owner()
                with SessionLocal() as db:
                    item = db.get(WorkItem, item_id)
                    payload["results"].append(result)
                    if result.get("status") == "success":
                        payload["next"] += 1
                        item.status = "done" if payload["next"] == len(payload["steps"]) else "ready"
                    else:
                        item.status = "failed"   # a failure never advances the plan
                    item.payload = json.dumps(payload); db.commit()
                    return view(item)
            except BaseException:
                # Locked or crashed before the result was saved: the outcome is unknown.
                try:
                    with SessionLocal() as db:
                        item = db.get(WorkItem, item_id)
                        if item is not None and item.status == "running":
                            item.status = "interrupted"; db.commit()
                except Exception:
                    pass  # database closed by lock; recover_interrupted() handles it at next unlock
                raise
        finally:
            work_lock.release()

    @router.get("/memory")
    def memories(q: str = ""):
        with SessionLocal() as db:
            query = db.query(MemoryItem)
            if q:
                query = query.filter(MemoryItem.content.contains(q[:200], autoescape=True))
            return [{"id": row.id, "content": row.content, "category": row.category} for row in query.limit(200)]

    @router.post("/memory")
    def remember(body: MemoryBody):
        from app.core.memory_service import memory_service
        with SessionLocal() as db:
            if not memory_service.remember(db, body.content):
                raise HTTPException(400, "Memory was rejected or already exists. Keep credentials in the vault.")
        return {"saved": True}

    @router.post("/memory/{item_id}/delete")
    def forget(item_id: str, body: ConfirmBody):
        require_pin(body.pin, "Enter your PIN to forget this memory.")
        with SessionLocal() as db:
            item = db.get(MemoryItem, item_id)
            if item is None:
                raise HTTPException(404, "Memory not found.")
            db.delete(item); db.commit()
        return {"deleted": True}

    @router.get("/history")
    def history():
        with SessionLocal() as db:
            return [{"id": row.id, "title": row.title, "created_at": row.created_at} for row in
                    db.query(Thread).order_by(Thread.created_at.desc()).limit(100)]

    @router.get("/history/{thread_id}")
    def messages(thread_id: str):
        with SessionLocal() as db:
            return [{"id": row.id, "role": row.role, "content": row.content} for row in
                    db.query(Message).filter_by(thread_id=thread_id).order_by(Message.id).limit(500)]

    @router.get("/skills")
    def skills():
        from app.core.skill_router import skill_router
        return [{"name": name, "description": record.manifest.description,
                 "enabled": skill_enabled(name), "execution": "in-process",
                 "capabilities": [c.value for c in record.manifest.required_capabilities]}
                for name, record in skill_router._skills.items()]

    @router.post("/skills/{name}")
    def set_skill(name: str, body: SkillBody):
        from app.core.skill_router import skill_router
        if name not in skill_router._skills:
            raise HTTPException(404, "Skill not found.")
        require_pin(body.pin, "Enter your PIN to change skill permissions.")
        with SessionLocal() as db:
            item = db.get(WorkItem, "skill:" + name)
            if item is None:
                item = WorkItem(id="skill:" + name, kind="skill_setting", title=name, payload="{}")
                db.add(item)
            item.status = "enabled" if body.enabled else "disabled"; db.commit()
        return {"enabled": body.enabled}

    @router.get("/privacy")
    def privacy():
        from app.core.egress import egress_guard
        with SessionLocal() as db:
            counts = {"conversations": db.query(Thread).count(), "messages": db.query(Message).count(),
                      "memories": db.query(MemoryItem).count(), "research": db.query(ResearchEntry).count(),
                      "work_items": db.query(WorkItem).filter(WorkItem.kind != "skill_setting").count()}
        return {"counts": counts, "storage": "SQLCipher encrypted database; closed when locked",
                "audio": "Dictation audio is held in memory only", "network": egress_guard.status(),
                "integrations": "Email and calendar are local drafts; no external accounts connected"}

    @router.post("/emergency-stop")
    def emergency():
        from app.core.resource_governor import resource_governor
        from app.core.ai_service import ai_service
        from app.core.safe_process import safe_process
        from app.core.egress import egress_guard
        resource_governor.set_user_paused(True)
        egress_guard.set_offline(True)
        for job in list(safe_process.active_processes):
            safe_process.cancel_job(job)
        ai_service.unload_model()
        import sys as _sys
        voice = _sys.modules.get("app.core.voice_service")
        if voice is not None:
            voice.voice_service.stop("emergency-stop")
        vault.lock("emergency-stop")
        return {"stopped": True}

    return router
