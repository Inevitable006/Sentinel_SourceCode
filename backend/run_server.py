import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("SENTINEL_BACKEND_PORT", 8000))
    print(f"Starting Sentinel API Server on port {port}...")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
