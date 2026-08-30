import json
import os
from app.core.paths import SENTINEL_DATA_DIR, MODELS_DIR

REGISTRY_FILE = SENTINEL_DATA_DIR / "models.json"

DEFAULT_REGISTRY = {
    "active_profile": "lightweight",
    "profiles": {
        "lightweight": {
            "name": "Qwen 2.5 1.5B (Lightweight)",
            "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "tier": "lightweight",
            "n_ctx": 2048,
            "n_threads": 4,
            "n_gpu_layers": -1,
            "description": "Fast everyday responses. Uses minimal RAM and CPU."
        },
        "balanced": {
            "name": "Llama 3.2 3B (Balanced)",
            "filename": "llama-3.2-3b-instruct-q4_k_m.gguf",
            "tier": "balanced",
            "n_ctx": 4096,
            "n_threads": 6,
            "n_gpu_layers": -1,
            "description": "Better reasoning when PC resources are available."
        },
        "heavy": {
            "name": "Qwen 2.5 7B (Heavy)",
            "filename": "qwen2.5-7b-instruct-q4_k_m.gguf",
            "tier": "heavy",
            "n_ctx": 4096,
            "n_threads": 6,
            "n_gpu_layers": -1,
            "description": "Maximum safe VRAM capacity for complex reasoning."
        }
    }
}

class ModelRegistry:
    def __init__(self):
        self._load()

    def _load(self):
        if not REGISTRY_FILE.exists():
            self.data = DEFAULT_REGISTRY.copy()
            self._save()
        else:
            try:
                with open(REGISTRY_FILE, "r") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = DEFAULT_REGISTRY.copy()
                
    def _save(self):
        with open(REGISTRY_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    def get_active_profile(self):
        active_id = self.data.get("active_profile", "lightweight")
        return self.data.get("profiles", {}).get(active_id, None)

    def set_active_profile(self, profile_id: str):
        if profile_id in self.data.get("profiles", {}):
            self.data["active_profile"] = profile_id
            self._save()
            return True
        return False

    def get_all_profiles(self):
        return self.data.get("profiles", {})

    def get_model_path(self, filename: str):
        return MODELS_DIR / filename

model_registry = ModelRegistry()
