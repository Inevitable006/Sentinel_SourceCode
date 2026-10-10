"""System Watch API: status, check now, "this is fine", and an owner-approved Defender quick scan."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.vault import vault
from app.core.system_watch import system_watch, POWERSHELL

_scan = {"running": False, "result": None}


class PinBody(BaseModel):
    pin: str | None = None


def create_watch_router(verify_session_token, require_pin):
    router = APIRouter(prefix="/api/watch", dependencies=[Depends(verify_session_token)])

    def require_unlocked():
        if not vault.is_unlocked():
            raise HTTPException(423, "Unlock Sentinel first.")

    @router.get("/status")
    def status():
        require_unlocked()
        return {**system_watch.status(), "defender_scan": dict(_scan)}

    @router.post("/check")
    async def check():
        require_unlocked()
        result = await asyncio.to_thread(system_watch.run_check)
        if result.get("status") == "busy":
            raise HTTPException(409, "A check is already running.")
        return result

    @router.post("/alerts/{alert_id:path}/accept")
    def accept(alert_id: str, body: PinBody):
        require_unlocked()
        # Accepting changes what counts as normal, so it needs a fresh PIN.
        require_pin(body.pin, "Enter your PIN to mark this as fine.")
        if not system_watch.accept(alert_id):
            raise HTTPException(404, "Alert not found.")
        return {"accepted": True}

    @router.post("/defender-scan")
    async def defender_scan(body: PinBody):
        require_unlocked()
        require_pin(body.pin, "Enter your PIN to start a Windows Defender quick scan.")
        if _scan["running"]:
            raise HTTPException(409, "A scan is already running.")
        from app.core.safe_process import safe_process
        _scan.update(running=True, result=None)

        def run():
            # Fixed command: a quick scan with Windows' own antivirus. Nothing is deleted by Sentinel.
            ok, out, err = safe_process.run_command(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", "Start-MpScan -ScanType QuickScan"],
                timeout_seconds=1800, job_id="defender-scan")
            _scan.update(running=False, result="Quick scan finished. Open Windows Security → Protection history for results."
                         if ok else f"Quick scan did not complete: {(err or '').strip()[:200]}")
            system_watch.run_check()

        asyncio.get_running_loop().run_in_executor(None, run)
        return {"started": True}

    return router
