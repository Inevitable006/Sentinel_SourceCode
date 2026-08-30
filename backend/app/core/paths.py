import os
from pathlib import Path

# Get the AppData roaming directory
APPDATA_DIR = os.getenv("APPDATA")
if not APPDATA_DIR:
    # Fallback if not set
    APPDATA_DIR = str(Path.home() / "AppData" / "Roaming")

SENTINEL_DATA_DIR = Path(APPDATA_DIR) / "sentinel"

# Specific subdirectories
DB_PATH = SENTINEL_DATA_DIR / "jarvis.db"
MODELS_DIR = SENTINEL_DATA_DIR / "models"
LOGS_DIR = SENTINEL_DATA_DIR / "logs"

def ensure_paths():
    """Ensure all required directories exist."""
    SENTINEL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
