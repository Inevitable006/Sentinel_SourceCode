import os
import sys
import requests
from pathlib import Path

# Add the parent directory to sys.path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.paths import MODELS_DIR

# Model configuration (ModelScope mirror to bypass Zscaler)
URL = "https://modelscope.cn/models/qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/master/qwen2.5-1.5b-instruct-q4_k_m.gguf"
FILENAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"

def download_model():
    print(f"Ensuring model directory exists: {MODELS_DIR}")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    target_path = MODELS_DIR / FILENAME
    
    if target_path.exists():
        if target_path.stat().st_size > 100 * 1024 * 1024: # basic check if it's not an html block page
            print(f"Model already exists at: {target_path}")
            return str(target_path)
        else:
            print(f"Found invalid/incomplete file at {target_path}. Deleting...")
            target_path.unlink()
        
    print(f"Downloading {FILENAME} from ModelScope (bypassing Zscaler)...")
    try:
        # verify=False to bypass SSL intercept issues
        with requests.get(URL, stream=True, verify=False) as r:
            r.raise_for_status()
            with open(target_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print(f"Download complete: {target_path}")
        return str(target_path)
    except Exception as e:
        print(f"Error downloading model: {e}")
        if target_path.exists():
            target_path.unlink()
        return None

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    download_model()
