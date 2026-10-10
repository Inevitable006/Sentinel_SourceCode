"""Authenticated dictation endpoints; transcripts are drafts, never executed commands."""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
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

    # ── Spoken replies: choose a male or female voice and the speed ──
    @router.get("/voices")
    async def voices():
        require_ready()
        from app.core.voice_service import voice_service
        return await asyncio.to_thread(voice_service.settings)

    @router.post("/voices")
    async def choose_voice(body: VoiceChoice):
        require_ready()
        from app.core.voice_service import voice_service
        try:
            return await asyncio.to_thread(voice_service.set_voice, body.voice_id, body.rate)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @router.post("/voices/preview")
    def preview():
        require_ready()
        from app.core.voice_service import voice_service
        voice_service.stop("preview")
        voice_service.speak("Hello, I am Sentinel. This is how I will sound.")
        return {"speaking": True}

    return router


class VoiceChoice(BaseModel):
    voice_id: str | None = None
    rate: int | None = None
