"""Male / female voice choice and speed for spoken replies."""
import json
import time
from types import SimpleNamespace

import pytest

MALE = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Test\\DAVID"
FEMALE = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Test\\ZIRA"


class FakeEngine:
    def __init__(self):
        self.props, self.spoken = {}, []
    def getProperty(self, name):
        return [SimpleNamespace(id=MALE, name="Microsoft David Desktop - English", gender="male"),
                SimpleNamespace(id=FEMALE, name="Microsoft Zira Desktop - English", gender="female")]
    def setProperty(self, name, value): self.props[name] = value
    def say(self, text): self.spoken.append((self.props.get("voice"), self.props.get("rate"), text))
    def runAndWait(self): pass
    def stop(self): pass


@pytest.fixture
def service(monkeypatch, tmp_path):
    import pyttsx3
    from app.core import voice_service as module
    engine = FakeEngine()
    monkeypatch.setattr(pyttsx3, "init", lambda: engine)
    monkeypatch.setattr(module, "_settings_file", lambda: tmp_path / "voice.json")
    return module.VoiceService(), engine, tmp_path / "voice.json"


def test_lists_male_and_female_voices(service):
    svc, _, _ = service
    voices = svc.settings()["voices"]
    assert {v["gender"] for v in voices} == {"male", "female"}
    assert [v["name"] for v in voices] == ["Microsoft David", "Microsoft Zira"]


def test_choice_is_applied_and_saved(service):
    svc, engine, file = service
    svc.set_voice(FEMALE, 200)
    svc.speak("Hello there.")
    for _ in range(50):
        if engine.spoken:
            break
        time.sleep(0.02)
    assert engine.spoken == [(FEMALE, 200, "Hello there.")]
    assert json.loads(file.read_text()) == {"voice_id": FEMALE, "rate": 200}


def test_unknown_voice_and_bad_speed_are_refused(service):
    svc, _, _ = service
    with pytest.raises(ValueError):
        svc.set_voice("HKEY_LOCAL_MACHINE\\SOFTWARE\\Evil")
    with pytest.raises(ValueError):
        svc.set_voice(rate=5000)


def test_saved_choice_is_used_after_restart(service, monkeypatch):
    svc, engine, file = service
    svc.set_voice(MALE, 150)
    from app.core import voice_service as module
    again = module.VoiceService()
    assert again.settings()["voice_id"] == MALE and again.settings()["rate"] == 150


def test_routes_require_unlock(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import speech_routes
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "voice-token")
    monkeypatch.setattr(speech_routes.vault, "is_unlocked", lambda: False)
    web = TestClient(app)
    assert web.get("/api/voice/voices", headers={"X-Sentinel-Session": "voice-token"}).status_code == 423
