"""
Model profiles (models.json in the data folder).

"auto" (the default since Phase 1b) lets Sentinel pick: the biggest downloaded model that fits in
the free VRAM runs on the GPU, otherwise the 1.5B model on the CPU (see ai_service.py).
Registry files from before Phase 1b have no "version"; they get the "auto" profile, and if they
still use the old default ("lightweight") they are switched to "auto". The owner can pick any
profile again in Settings.
"""
import copy
import json
import os

from app.core.paths import SENTINEL_DATA_DIR, MODELS_DIR

REGISTRY_FILE = SENTINEL_DATA_DIR / "models.json"
REGISTRY_VERSION = 2

AUTO_PROFILE = {
    "name": "Auto (best for this PC)",
    "tier": "auto",
    "description": "Biggest model that fits: 7B on the GPU when there is room, otherwise 1.5B (GPU, then CPU).",
}

DEFAULT_REGISTRY = {
    "version": REGISTRY_VERSION,
    "active_profile": "auto",
    "profiles": {
        "auto": AUTO_PROFILE,
        "lightweight": {
            "name": "Qwen 2.5 1.5B (Lightweight)",
            "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
            "chat_format": "chatml",
            "tier": "lightweight",
            "n_ctx": 2048,
            "n_threads": 4,
            "n_gpu_layers": -1,
            "description": "Fast everyday responses. Uses minimal RAM and CPU."
        },
        "balanced": {
            "name": "Llama 3.2 3B (Balanced)",
            "filename": "llama-3.2-3b-instruct-q4_k_m.gguf",
            "chat_format": "llama3",
            "tier": "balanced",
            "n_ctx": 4096,
            "n_threads": 6,
            "n_gpu_layers": -1,
            "description": "Better reasoning when PC resources are available."
        },
        "heavy": {
            "name": "Qwen 2.5 7B (Heavy)",
            "filename": "qwen2.5-7b-instruct-q4_k_m.gguf",
            "chat_format": "chatml",
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
            self.data = copy.deepcopy(DEFAULT_REGISTRY)
            self._save()
            return
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            if not isinstance(self.data, dict) or not isinstance(self.data.get("profiles"), dict):
                raise ValueError("unexpected layout")
        except Exception:
            # Unreadable file: use the defaults for this run and leave the file as it is.
            self.data = copy.deepcopy(DEFAULT_REGISTRY)
            return
        if self._migrate():
            self._save()

    def _migrate(self) -> bool:
        if int(self.data.get("version", 1) or 1) >= REGISTRY_VERSION:
            return False
        profiles = self.data["profiles"]
        # "auto" first, so it is the first choice in Settings.
        self.data["profiles"] = {"auto": copy.deepcopy(AUTO_PROFILE),
                                 **{k: v for k, v in profiles.items() if k != "auto"}}
        if self.data.get("active_profile", "lightweight") == "lightweight":
            self.data["active_profile"] = "auto"
        self.data["version"] = REGISTRY_VERSION
        return True

    def _save(self):
        tmp = REGISTRY_FILE.with_name(REGISTRY_FILE.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)
        os.replace(tmp, REGISTRY_FILE)

    def get_active_id(self) -> str:
        profiles = self.data.get("profiles", {})
        active = self.data.get("active_profile", "auto")
        if active in profiles:
            return active
        return "auto" if "auto" in profiles else next(iter(profiles), "auto")

    def get_active_profile(self):
        return self.data.get("profiles", {}).get(self.get_active_id(), None)

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
