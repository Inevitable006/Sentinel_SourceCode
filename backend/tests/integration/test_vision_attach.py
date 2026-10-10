"""F05: an image the owner attaches is validated and actually analyzed in chat."""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

TOKEN = "vision-test-token"


def png(size=(8, 8)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def web(monkeypatch):
    from app.main import app
    from app import vision_routes
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", TOKEN)
    monkeypatch.setattr(vision_routes.vault, "is_unlocked", lambda: True)
    return TestClient(app)


def upload(web, data, ctype="image/png", token=TOKEN):
    return web.post("/api/vision/upload", content=data, headers={"X-Sentinel-Session": token, "Content-Type": ctype})


def test_upload_rules(web, monkeypatch):
    from app import vision_routes
    assert upload(web, png(), token="wrong").status_code == 401
    assert upload(web, b"not an image").status_code == 400
    assert upload(web, png(), ctype="image/gif").status_code == 415
    assert upload(web, b"x" * (15 * 1024 * 1024 + 1)).status_code == 413
    ok = upload(web, png())
    assert ok.status_code == 200 and len(ok.json()["image_id"]) == 32
    monkeypatch.setattr(vision_routes.vault, "is_unlocked", lambda: False)
    assert upload(web, png()).status_code == 423


def test_inbox_is_single_use_and_cleared_on_lock():
    from app.core.vision_service import image_inbox
    image_id = image_inbox.put(b"data")
    assert image_inbox.take(image_id) == b"data"
    assert image_inbox.take(image_id) is None
    other = image_inbox.put(b"data")
    image_inbox.clear("locked")
    assert image_inbox.take(other) is None
    from app.core.vault import vault
    assert image_inbox.clear in vault._listeners


def _chat_with_image(web, image_id):
    from app.db.database import SessionLocal
    from app.db.models import Message
    with web.websocket_connect("/ws/chat", subprotocols=["sentinel.v1", TOKEN]) as ws:
        thread_id = None
        for _ in range(5):
            msg = ws.receive_json()
            if msg["type"] == "thread":
                thread_id = msg["thread_id"]
                break
        ws.send_json({"text": "What colour is this?", "image_id": image_id, "voice_enabled": False})
        for _ in range(20):
            msg = ws.receive_json()
            if msg["type"] in ("reply", "error", "reply_end") or msg.get("state") == "COMPLETED":
                break
    with SessionLocal() as db:
        return [m.content for m in db.query(Message).filter_by(thread_id=thread_id, role="system")]


def test_attached_image_is_analyzed_in_chat(web, monkeypatch):
    from app.core.vision_service import vision_service
    seen = {}
    class FakeAdapter:
        def is_available(self): return True
        def analyze(self, img, prompt):
            seen["size"], seen["prompt"] = img.size, prompt
            return {"ok": True, "error": None, "content": "A small red square."}
    monkeypatch.setattr(vision_service, "adapter", FakeAdapter())
    image_id = upload(web, png((8, 8))).json()["image_id"]
    notes = _chat_with_image(web, image_id)
    assert seen == {"size": (8, 8), "prompt": "What colour is this?"}
    assert any("A small red square." in n for n in notes)


def test_missing_vision_model_is_reported_not_guessed(web, monkeypatch):
    from app.core.vision_service import vision_service
    class NoModel:
        def is_available(self): return False
    monkeypatch.setattr(vision_service, "adapter", NoModel())
    image_id = upload(web, png()).json()["image_id"]
    notes = _chat_with_image(web, image_id)
    assert any("could not be analyzed because no local vision model is installed" in n for n in notes)
