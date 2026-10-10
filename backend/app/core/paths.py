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

def workspace_root() -> Path:
    """The one folder workspace tools may list. SENTINEL_WORKSPACE overrides it;
    the default is the project folder this backend runs from (it follows a moved project)."""
    configured = os.getenv("SENTINEL_WORKSPACE")
    if configured:
        return Path(os.path.realpath(configured))
    return Path(os.path.realpath(Path(__file__).resolve().parents[3]))

def ensure_paths():
    """Ensure all required directories exist."""
    SENTINEL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
