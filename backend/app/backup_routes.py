"""Encrypted backup API. Creating/downloading needs Sentinel unlocked + a fresh PIN;
restoring needs Sentinel locked and the PIN or recovery key (sent in a header, never in a URL)."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core import backup
from app.core.vault import vault


class PinBody(BaseModel):
    pin: str | None = None


async def _read_body(request: Request) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > backup.MAX_BACKUP_BYTES:
            raise HTTPException(413, "File too large.")
    return bytes(data)


def create_backup_router(verify_session_token, require_pin):
    router = APIRouter(prefix="/api/backup", dependencies=[Depends(verify_session_token)])

    @router.get("")
    def listing():
        if not vault.is_unlocked():
            raise HTTPException(423, "Unlock Sentinel first.")
        return {"backups": backup.list_backups(), "folder": str(backup.BACKUP_DIR)}

    @router.post("/create")
    async def create(body: PinBody):
        require_pin(body.pin, "Enter your PIN to create a backup.")
        try:
            path = await asyncio.to_thread(backup.create_backup)
        except backup.BackupError as e:
            raise HTTPException(400, str(e)) from None
        return {"name": path.name, "size": path.stat().st_size}

    @router.post("/download/{name}")
    def download(name: str, body: PinBody):
        require_pin(body.pin, "Enter your PIN to save a backup copy.")
        try:
            path = backup.backup_path(name)
        except backup.BackupError as e:
            raise HTTPException(404, str(e)) from None
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)

    def _secret(request: Request):
        kind = request.headers.get("x-sentinel-restore-kind", "")
        secret = request.headers.get("x-sentinel-restore-secret", "")
        if kind not in ("pin", "recovery") or not secret:
            raise HTTPException(400, "Enter the PIN or recovery key for this backup.")
        return kind, secret

    @router.post("/verify")
    async def verify(request: Request):
        kind, secret = _secret(request)
        data = await _read_body(request)
        try:
            return await asyncio.to_thread(backup.verify_backup, data, secret, kind)
        except backup.BackupError as e:
            raise HTTPException(400, str(e)) from None

    @router.post("/restore")
    async def restore(request: Request):
        kind, secret = _secret(request)
        data = await _read_body(request)
        try:
            return await asyncio.to_thread(backup.restore_backup, data, secret, kind)
        except backup.BackupError as e:
            raise HTTPException(400, str(e)) from None

    return router
