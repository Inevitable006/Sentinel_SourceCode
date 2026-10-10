"""Authenticated dictation endpoints; transcripts are drafts, never executed commands."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.speech_input import MAX_AUDIO_BYTES, SpeechError, speech_input
from app.core.vault import vault
from app.core.resource_governor import resource_governor, SystemState

vault.add_lock_listener(speech_input.invalidate)


def create_speech_router(verify_session_token):
    router = APIRouter(prefix="/api/voice", dependencies=[Depends(verify_session_token)])

    def require_ready():
        if not vault.is_unlocked():
            raise HTTPException(423, "Unlock Sentinel before using dictation.")

    @router.get("/status")
    def status():
        require_ready()
        return speech_input.status()

    @router.post("/transcribe")
    async def transcribe(request: Request):
        require_ready()
        blocked = (SystemState.HIGH_LOAD, SystemState.EMERGENCY, SystemState.USER_PAUSED)
        if resource_governor.state in blocked:
            raise HTTPException(409, "Dictation is paused while Sentinel is paused or the computer is busy.")
        epoch = speech_input.epoch
        if request.headers.get("content-type", "").split(";")[0].strip() != "audio/wav":
            raise HTTPException(415, "Send a WAV recording.")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_AUDIO_BYTES:
                raise HTTPException(413, "Recording is too large. Limit dictation to 30 seconds.")
            data.extend(chunk)
        def allowed():
            return (speech_input.epoch == epoch and vault.is_unlocked()
                    and resource_governor.state not in blocked)
        try:
            result = await asyncio.to_thread(speech_input.transcribe, bytes(data), allowed)
        except SpeechError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        if not allowed():
            raise HTTPException(423, "Dictation was interrupted. Please try again.")
        return result

    return router
