"""Mounted under the authenticated, unlocked Workspace router."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core import google_workspace as google


class PinBody(BaseModel):
    pin: str | None = None


class ClientBody(PinBody):
    client_id: str = Field(min_length=1, max_length=300)
    client_secret: str = Field(default="", max_length=1000)


def create_google_router(require_pin):
    router = APIRouter(prefix="/google")

    def local(action, *args):
        try:
            return action(*args)
        except google.GoogleError as e:
            raise HTTPException(400, str(e)) from None

    async def remote(action):
        try:
            return await action()
        except google.GoogleError as e:
            raise HTTPException(400, str(e)) from None

    @router.get("/status")
    def status():
        return local(google.status)

    @router.post("/configure")
    def configure(body: ClientBody):
        require_pin(body.pin, "Enter your PIN to configure Google access.")
        local(google.configure, body.client_id, body.client_secret)
        return {"configured": True}

    @router.post("/start")
    def start(body: PinBody):
        require_pin(body.pin, "Enter your PIN to connect Google.")
        return local(google.start)

    @router.post("/finish")
    async def finish(body: PinBody):
        require_pin(body.pin, "Enter your PIN to finish connecting Google.")
        return await remote(google.finish)

    @router.post("/disconnect")
    def disconnect(body: PinBody):
        require_pin(body.pin, "Enter your PIN to remove Google credentials.")
        return local(google.disconnect)

    @router.post("/messages")
    async def messages():
        return await remote(google.messages)

    @router.post("/events")
    async def events():
        return await remote(google.events)

    return router
