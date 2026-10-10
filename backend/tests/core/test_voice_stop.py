"""F15: lock / emergency stop / Voice off silence queued and ongoing speech."""
import sys
import threading
import time

import pytest


class FakeEngine:
    def __init__(self):
        self.spoken, self.stops = [], 0
        self._wake = threading.Event()
    def setProperty(self, *a): pass
    def say(self, text): self.spoken.append(text)
    def runAndWait(self):
        self._wake.wait(0.3)   # a slow utterance that stop() can cut short
        self._wake.clear()
    def stop(self):
        self.stops += 1
        self._wake.set()


@pytest.fixture
def voice(monkeypatch):
    import pyttsx3
    engine = FakeEngine()
    monkeypatch.setattr(pyttsx3, "init", lambda: engine)
    from app.core import voice_service as module
    service = module.VoiceService()
    monkeypatch.setattr(module, "voice_service", service)
    monkeypatch.setitem(sys.modules, "app.core.voice_service", module)
    for _ in range(50):
        if service._engine is engine:
            break
        time.sleep(0.01)
    return service, engine


def _speak_many(service):
    service.speak("One. Two. Three. Four. Five. Six. Seven. Eight.")
    time.sleep(0.1)   # first sentence is being spoken


def test_lock_stops_speech(voice):
    from app.main import _stop_speech
    service, engine = voice
    _speak_many(service)
    _stop_speech("locked")
    assert service.pending() == 0 and engine.stops >= 1
    time.sleep(0.5)
    assert len(engine.spoken) <= 2, engine.spoken


def test_lock_listener_is_registered():
    from app.main import _stop_speech
    from app.core.vault import vault
    assert _stop_speech in vault._listeners


def test_new_speech_after_stop_still_works(voice):
    service, engine = voice
    _speak_many(service)
    service.stop()
    before = len(engine.spoken)
    service.speak("Hello again.")
    time.sleep(0.5)
    assert engine.spoken[before:] == ["Hello again."]
