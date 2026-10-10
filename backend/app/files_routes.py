"""Recent file actions and their undo window."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import file_ops
from app.core.vault import vault


class PinBody(BaseModel):
    pin: str | None = None


def create_files_router(verify_session_token, require_pin):
    router = APIRouter(prefix="/api/files", dependencies=[Depends(verify_session_token)])

    def unlocked():
        if not vault.is_unlocked():
            raise HTTPException(423, "Unlock Sentinel first.")

    @router.get("/actions")
    def actions():
        unlocked()
        return {"folder": str(file_ops.files_root()), "undo_minutes": file_ops.UNDO_SECONDS // 60, "actions": file_ops.recent()}

    @router.post("/actions/{action_id}/undo")
    def undo(action_id: str, body: PinBody):
        unlocked()
        require_pin(body.pin, "Enter your PIN to undo this file action.")
        try:
            return {"message": file_ops.undo(action_id)}
        except file_ops.FileOpError as e:
            raise HTTPException(409, str(e)) from None

    return router
