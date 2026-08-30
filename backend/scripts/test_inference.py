import os
import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.ai_service import ai_service

def test_inference():
    print("Testing AI Service...")
    success = ai_service.load_model()
    if not success:
        print("Failed to load model.")
        sys.exit(1)
        
    print("Model loaded. Sending prompt: 'Hello JARVIS, are you online?'")
    
    print("\nJARVIS Response: ", end="", flush=True)
    for chunk in ai_service.generate_stream("Hello JARVIS, are you online?"):
        print(chunk, end="", flush=True)
    print("\n\nTest complete.")

if __name__ == "__main__":
    test_inference()
