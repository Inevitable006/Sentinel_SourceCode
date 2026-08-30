import webview
import threading
import uvicorn
import time
import os
import sys
from pathlib import Path

# Ensure we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent))

def start_backend():
    """Run the FastAPI server in a separate thread."""
    from app.main import app
    print("Starting FastAPI Backend...")
    # Run uvicorn programmatically
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

if __name__ == '__main__':
    # Start the backend server in a background daemon thread
    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()
    
    # Wait a brief moment for the server to bind
    time.sleep(1)

    print("Launching Sentinel Desktop Shell...")
    
    # Create a frameless/modern native window pointing to the React frontend
    # Note: the React frontend must be running on port 5173
    window = webview.create_window(
        title='Sentinel',
        url='http://localhost:5173',
        width=1200,
        height=800,
        min_size=(800, 600),
        background_color='#0b0f19',
        frameless=False, # Set to True for custom chrome
        easy_drag=True
    )
    
    # Start the pywebview event loop
    webview.start(private_mode=False)
