"""Authenticated image attachment: the UI uploads an image the owner picked; it is checked and
kept in memory until the next chat message uses it. No file paths cross from the window."""
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.vault import vault
from app.core.vision_service import vision_service, image_inbox, VisionService

vault.add_lock_listener(image_inbox.clear)

ACCEPTED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp"}


def create_vision_router(verify_session_token):
    router = APIRouter(prefix="/api/vision", dependencies=[Depends(verify_session_token)])

    def require_unlocked():
        if not vault.is_unlocked():
            raise HTTPException(423, "Unlock Sentinel before attaching images.")

    @router.get("/status")
    def status():
        require_unlocked()
        available = vision_service.adapter.is_available()
        return {"available": available,
                "reason": None if available else "No local vision model is installed. Images cannot be analyzed yet."}

    @router.post("/upload")
    async def upload(request: Request):
        require_unlocked()
        if request.headers.get("content-type", "").split(";")[0].strip().lower() not in ACCEPTED_TYPES:
            raise HTTPException(415, "Attach a PNG, JPEG, WebP or BMP image.")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > VisionService.MAX_FILE_SIZE:
                raise HTTPException(413, "Image is too large (limit 15 MB).")
            data.extend(chunk)
        img = vision_service.load_image_bytes(bytes(data))
        if img is None:
            raise HTTPException(400, "This file is not a valid image, or it is too large.")
        img.close()
        return {"image_id": image_inbox.put(bytes(data))}

    return router
