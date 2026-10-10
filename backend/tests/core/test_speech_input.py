import io
import sys
import threading
import wave
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app.core import speech_input as speech


def wav(seconds=1, channels=1, width=2, rate=16000):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\0" * int(seconds * rate) * channels * width)
    return stream.getvalue()


@pytest.mark.parametrize("data", [b"", b"not a wave", wav(.1), wav(30.1),
                                       wav(channels=2), wav(width=1), wav(rate=8000), wav()[:-2]],
                         ids=["empty", "invalid", "too-short", "too-long", "stereo", "8-bit", "8-kHz", "truncated"])
def test_invalid_recordings_are_rejected(data):
    with pytest.raises(speech.SpeechError):
        speech.decode_audio(data)


def test_pcm_is_bounded_and_normalized():
    samples = speech.decode_audio(wav(30))
    assert len(samples) == 480000
    assert samples.dtype.name == "float32"
    assert not samples.any()


@pytest.fixture
def engine(monkeypatch):
    service = speech.SpeechInput()
    monkeypatch.setattr(speech, "verify_model", lambda: None)
    monkeypatch.setattr(service, "status", lambda: {"available": True})
    model = Mock()
    model.transcribe.return_value = (iter([SimpleNamespace(text=" Hello"), SimpleNamespace(text=" world")]),
                                     SimpleNamespace(language="en"))
    constructor = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=constructor))
    return service, constructor, model


def test_local_only_transcription(engine):
    service, constructor, model = engine
    assert service.transcribe(wav(), lambda: True) == {"text": "Hello world", "language": "en"}
    constructor.assert_called_once_with(str(speech.MODEL_DIR), device="cpu", compute_type="int8",
                                        cpu_threads=4, num_workers=1, local_files_only=True)
    assert model.transcribe.call_args.kwargs["vad_filter"] is True
    assert not service._busy.locked()


def test_lock_during_transcription_discards_output(engine):
    service, _, model = engine
    epoch = service.epoch
    def segments():
        yield SimpleNamespace(text="private")
        service.invalidate()
    model.transcribe.return_value = (segments(), SimpleNamespace(language="en"))
    with pytest.raises(speech.SpeechError) as error:
        service.transcribe(wav(), lambda: service.epoch == epoch)
    assert error.value.status == 423
    assert not service._busy.locked()


def test_concurrent_recognition_is_rejected(engine):
    service, _, model = engine
    started, release = threading.Event(), threading.Event()
    def segments():
        started.set()
        assert release.wait(5)
        yield SimpleNamespace(text="one")
    model.transcribe.return_value = (segments(), SimpleNamespace(language="en"))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(1) as executor:
        future = executor.submit(service.transcribe, wav(), lambda: True)
        try:
            assert started.wait(5)
            with pytest.raises(speech.SpeechError) as error:
                service.transcribe(wav(), lambda: True)
            assert error.value.status == 409
        finally:
            release.set()
        assert future.result()["text"] == "one"


def test_private_native_exception_is_not_returned(engine):
    service, constructor, _ = engine
    constructor.side_effect = RuntimeError("private recording contents")
    with pytest.raises(speech.SpeechError) as error:
        service.transcribe(wav(), lambda: True)
    assert error.value.status == 503
    assert "private recording" not in str(error.value)
    assert not service._busy.locked()


def test_missing_tokenizer_blocks_model_loading(tmp_path, monkeypatch):
    for name in ("model.bin", "config.json"):
        (tmp_path / name).write_bytes(b"test")
    monkeypatch.setattr(speech, "MODEL_DIR", tmp_path)
    service = speech.SpeechInput()
    assert service.status()["available"] is False
    with pytest.raises(speech.SpeechError) as error:
        service.transcribe(wav(), lambda: True)
    assert error.value.status == 503


def test_model_integrity_rejects_changed_file(tmp_path, monkeypatch):
    import hashlib
    import json
    names = ("model.bin", "config.json", "tokenizer.json")
    expected = {}
    for name in names:
        (tmp_path / name).write_bytes(b"original")
        expected[name] = hashlib.sha256(b"original").hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": expected}))
    monkeypatch.setattr(speech, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(speech, "MODEL_MANIFEST", manifest)
    speech.verify_model()
    (tmp_path / "model.bin").write_bytes(b"changed")
    with pytest.raises(speech.SpeechError, match="integrity"):
        speech.verify_model()


def test_blocked_runtime_is_unavailable_before_microphone_use(tmp_path, monkeypatch):
    import builtins
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_bytes(b"test")
    monkeypatch.setattr(speech, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(speech.importlib.util, "find_spec", lambda name: object())
    real_import = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("An Application Control policy has blocked this file.")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", blocked)
    status = speech.SpeechInput().status()
    assert status["available"] is False
    assert "Application Control" in status["reason"]


@pytest.fixture
def client(monkeypatch):
    from app.main import app
    from app import speech_routes as routes
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "speech-test-token")
    monkeypatch.setattr(routes.vault, "is_unlocked", lambda: True)
    monkeypatch.setattr(routes.resource_governor, "state", routes.SystemState.IDLE)
    monkeypatch.setattr(routes.speech_input, "transcribe", lambda data, allowed: {"text": "a draft", "language": "en"})
    return TestClient(app), routes


HEADERS = {"X-Sentinel-Session": "speech-test-token", "Content-Type": "audio/wav"}


def test_routes_require_token_and_unlock(client, monkeypatch):
    web, routes = client
    assert web.get("/api/voice/status").status_code == 422
    assert web.post("/api/voice/transcribe", content=wav(), headers={**HEADERS, "X-Sentinel-Session": "bad"}).status_code == 401
    monkeypatch.setattr(routes.vault, "is_unlocked", lambda: False)
    assert web.get("/api/voice/status", headers=HEADERS).status_code == 423
    assert web.post("/api/voice/transcribe", content=wav(), headers=HEADERS).status_code == 423


def test_route_enforces_size_type_and_resource_limits(client, monkeypatch):
    web, routes = client
    assert web.post("/api/voice/transcribe", content=b"x", headers={**HEADERS, "Content-Type": "audio/webm"}).status_code == 415
    assert web.post("/api/voice/transcribe", content=b"x" * (speech.MAX_AUDIO_BYTES + 1), headers=HEADERS).status_code == 413
    monkeypatch.setattr(routes.resource_governor, "state", routes.SystemState.USER_PAUSED)
    assert web.post("/api/voice/transcribe", content=wav(), headers=HEADERS).status_code == 409


def test_route_returns_only_a_draft(client):
    web, _ = client
    response = web.post("/api/voice/transcribe", content=wav(), headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"text": "a draft", "language": "en"}


def test_lock_and_unlock_cycle_invalidates_pending_request(client, monkeypatch):
    web, routes = client
    def transcribe(data, allowed):
        routes.speech_input.invalidate()
        assert not allowed()
        return {"text": "must be discarded", "language": "en"}
    monkeypatch.setattr(routes.speech_input, "transcribe", transcribe)
    response = web.post("/api/voice/transcribe", content=wav(), headers=HEADERS)
    assert response.status_code == 423
    assert "must be discarded" not in response.text


def _pinned_model(tmp_path, monkeypatch):
    import hashlib
    import json
    names = ("model.bin", "config.json", "tokenizer.json")
    for name in names:
        (tmp_path / name).write_bytes(name.encode())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": {n: hashlib.sha256(n.encode()).hexdigest() for n in names}}))
    monkeypatch.setattr(speech, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(speech, "MODEL_MANIFEST", manifest)
    monkeypatch.setattr(speech.importlib.util, "find_spec", lambda name: object())


@pytest.mark.parametrize("loads", [True, False])
def test_ready_only_when_the_model_really_loads(tmp_path, monkeypatch, loads):
    # F04: files and imports present is not enough; status must reflect a real model load.
    import sys
    import types
    _pinned_model(tmp_path, monkeypatch)
    def whisper_model(*args, **kwargs):
        if not loads:
            raise RuntimeError(f"Cannot load the vocabulary from {tmp_path}")
        return object()
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=whisper_model))
    status = speech.SpeechInput().status()
    assert status["available"] is loads
    if not loads:
        assert "cannot load" in status["reason"] and str(tmp_path) not in status["reason"]
