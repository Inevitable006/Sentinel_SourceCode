import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.memory_service import memory_service
from app.db.database import SessionLocal

@pytest.fixture
def override_deps():
    os.environ["SENTINEL_SESSION_TOKEN"] = "test_token"
    yield
    if "SENTINEL_SESSION_TOKEN" in os.environ:
        del os.environ["SENTINEL_SESSION_TOKEN"]

def test_v1_image_ingestion_websocket(override_deps):
    """
    V1-A: Tests that the WebSocket accepts the image_path payload 
    and securely injects it into the conversation memory as a system note.
    """
    client = TestClient(app)
    
    # Establish a websocket connection
    with client.websocket_connect("/ws/chat?token=test_token") as websocket:
        # Initial connect message from backend
        data = websocket.receive_json()
        assert data["type"] == "status"
        
        # Send a message with an image payload
        test_payload = {
            "text": "Please analyze this image",
            "image_path": "C:/fake/path/to/image.png",
            "voice_enabled": False
        }
        websocket.send_json(test_payload)
        
    # Query memory directly
    db = SessionLocal()
    try:
        # Find the most recent thread
        # In this simplistic setup, we just fetch all history from the latest thread
        from app.db.models import Thread
        latest_thread = db.query(Thread).order_by(Thread.created_at.desc()).first()
        assert latest_thread is not None
        
        history = memory_service.get_context_history(db, latest_thread.id, limit=20)
        
        # Check if the system note was successfully added
        image_note_found = False
        for msg in history:
            if "User attached an image: C:/fake/path/to/image.png" in msg.get("content", ""):
                image_note_found = True
                break
                
        assert image_note_found, "The image ingestion system note was not found in the conversation memory."
    finally:
        db.close()
