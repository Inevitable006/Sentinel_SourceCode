from abc import ABC, abstractmethod
from typing import Dict, Any
import PIL.Image

class VisionModelAdapter(ABC):
    """
    Abstract interface for vision model adapters.
    Ensures that Sentinel's core logic is decoupled from the underlying vision model implementation.
    """
    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the vision model is successfully loaded and ready for inference."""
        pass

    @abstractmethod
    def analyze(self, image: PIL.Image.Image, prompt: str) -> Dict[str, Any]:
        """
        Analyzes the provided image using the vision model.
        Accepts only a validated PIL.Image.Image.
        Returns a structured dictionary with the results or an error.
        """
        pass

class LocalVisionAdapter(VisionModelAdapter):
    """
    V1-B4 Stub Implementation of the Local Vision Adapter.
    Deliberately hardcoded to be unavailable until V1-B5.
    """
    def __init__(self, model_path: str = None):
        self.model_path = model_path
        # In B4, we don't download, load, or initialize any model.

    def is_available(self) -> bool:
        # V1-B4: Deliberately unavailable.
        return False

    def analyze(self, image: PIL.Image.Image, prompt: str) -> Dict[str, Any]:
        if not self.is_available():
            return {
                "ok": False,
                "error": "VISION_MODEL_UNAVAILABLE",
                "content": None
            }
        
        # B4 safety net - should never be reached
        return {
            "ok": False,
            "error": "VISION_MODEL_NOT_IMPLEMENTED",
            "content": None
        }
