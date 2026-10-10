""""What did Sentinel do?" — the audit log turned into plain sentences.

Reads the HMAC-chained audit log (and rotated files), newest first. Each tool run becomes one
entry: what it was, where the request came from (chat or a plan), whether you approved it, and
how it ended. Requests you never approved show as "not approved (declined or expired)".
The log holds tool names and outcomes only, never your search terms or file contents.
"""
import json
import time
from typing import Dict, List, Optional

MERGE_WINDOW = 15 * 60      # an approval and its run belong together if within this time


def _label(tool: str) -> str:
    from app.core.tool_registry import tool_registry
    tool_def = tool_registry.get_tool(tool or "")
    if tool_def and tool_def.tool_schema.description:
        first = tool_def.tool_schema.description.split(". ")[0].rstrip(".")
        return first[0].upper() + first[1:] if first else tool
    return (tool or "unknown action").replace("skill_", "").replace("_", " ")


def _read_entries() -> List[dict]:
    from app.core import audit_logger as al
    logger = al.audit_logger
    files = [logger._rotated(i) for i in range(al.KEEP_ROTATED, 0, -1)] + [logger.log_file]
    entries = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return entries


def _origins() -> Dict[str, str]:
    """Plan ids -> plan titles, so entries can say where a request came from."""
    try:
        from app.db.database import SessionLocal
        from app.db.models import WorkItem
        with SessionLocal() as db:
            return {r.id: r.title for r in db.query(WorkItem).filter(WorkItem.kind == "plan")}
    except Exception:
        return {}


def build_activity(days: float = 7, now: Optional[float] = None, entries: Optional[List[dict]] = None) -> dict:
    now = now or time.time()
    since = now - days * 86400
    entries = [e for e in (entries if entries is not None else _read_entries()) if e.get("timestamp", 0) >= since]
    plans = _origins()
    items: List[dict] = []
    pending: Dict[tuple, dict] = {}       # (tool, session) -> approval request waiting for its run

    def origin(session: str) -> str:
        if session in plans:
            return f"plan “{plans[session]}”"
        if session in ("plan-preview", "system-watch"):
            return "Sentinel"
        return "chat"

    for e in sorted(entries, key=lambda x: x.get("timestamp", 0)):
        kind, d = e.get("event_type"), e.get("details") or {}
        tool, session, ts = d.get("tool_name"), str(d.get("session_id", "")), e.get("timestamp", 0)
        key = (tool, session)
        if kind == "confirmation_requested":
            entry = {"time": ts, "action": _label(tool), "tool": tool, "from": origin(session),
                     "approval": "asked", "outcome": "not approved (declined or expired)", "status": "not_approved"}
            pending[key] = entry
            items.append(entry)
        elif kind in ("execution_success", "execution_failed"):
            entry = pending.pop(key, None)
            if entry is None or ts - entry["time"] > MERGE_WINDOW:
                entry = {"time": ts, "action": _label(tool), "tool": tool, "from": origin(session),
                         "approval": "not needed (read-only)"}
                items.append(entry)
            else:
                entry["approval"] = "approved by you"
            ok = kind == "execution_success"
            entry["status"] = "done" if ok else "failed"
            entry["outcome"] = (f"done in {float(d.get('duration', 0)):.1f} s" if ok
                                else f"failed: {d.get('error') or 'see the chat for details'}")
        elif kind == "execution_denied_skill_disabled":
            items.append({"time": ts, "action": _label(tool), "tool": tool, "from": origin(session), "approval": "—",
                          "status": "blocked", "outcome": f"blocked: the {d.get('skill')} skill is turned off"})
        elif kind == "token_validation_failed":
            entry = pending.pop(key, None) or {"time": ts, "action": _label(tool), "tool": tool, "from": origin(session)}
            if entry not in items:
                items.append(entry)
            entry.update(approval="approval rejected", status="blocked",
                         outcome="refused: the approval was invalid, expired or already used")
        elif kind == "policy_evaluation" and d.get("decision") == "deny":
            items.append({"time": ts, "action": _label(tool), "tool": tool, "from": origin(session), "approval": "—",
                          "status": "blocked", "outcome": f"refused by safety rules: {d.get('reason', '')}"})
        elif kind == "system_watch_offline":
            items.append({"time": ts, "action": "Switched Sentinel to Offline mode", "tool": None, "from": "System Watch",
                          "approval": "automatic (reversible)", "status": "done",
                          "outcome": "after a serious alert; turn Offline mode off in Settings when it is resolved"})
        elif kind == "skill_registration_failed":
            items.append({"time": ts, "action": f"Refused to load the {d.get('skill')} skill", "tool": None, "from": "Sentinel",
                          "approval": "—", "status": "blocked", "outcome": str(d.get("reason", ""))[:200]})
    items.sort(key=lambda x: x["time"], reverse=True)
    counts = {s: sum(1 for i in items if i.get("status") == s) for s in ("done", "failed", "blocked", "not_approved")}
    return {"days": days, "items": items[:300], "counts": counts}


def activity_with_integrity(days: float = 7) -> dict:
    from app.core.audit_logger import audit_logger
    result = build_activity(days)
    check = audit_logger.verify_log()
    result["integrity"] = {"ok": check["ok"], "entries": check["entries"],
                           "message": ("The activity log is intact." if check["ok"]
                                       else f"Warning: the activity log was changed ({check['problem']}). "
                                            "Entries after that point may not be trustworthy.")}
    return result
