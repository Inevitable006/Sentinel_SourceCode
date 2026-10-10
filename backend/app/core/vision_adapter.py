import os
import base64
import threading
from io import BytesIO
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
import PIL.Image

logger = logging.getLogger(__name__)

from app.core.resource_governor import resource_governor, SystemState

try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Llava15ChatHandler
    LLAMA_CPP_AVAILABLE = True
except (ImportError, RuntimeError):
    # RuntimeError catches "[WinError 4551] An Application Control policy has blocked this file" for DLLs
    LLAMA_CPP_AVAILABLE = False
    Llama = None
    Llava15ChatHandler = None

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
    V1-B5 Implementation of the Local Vision Adapter.
    Uses llama-cpp-python with a LLaVA-1.5 compatible GGUF and mmproj.
    """
    def __init__(self, model_path: str = None, proj_path: str = None):
        # Allow override via args, but default to environment variables
        self.model_path = model_path or os.environ.get("SENTINEL_VISION_MODEL_PATH")
        self.proj_path = proj_path or os.environ.get("SENTINEL_VISION_PROJ_PATH")
        self.lock = threading.Lock()
        self._llama = None

    def is_available(self) -> bool:
        """
        Validates that both model files exist locally and llama-cpp is installed.
        Does not automatically download models.
        """
        if not LLAMA_CPP_AVAILABLE:
            return False
        if not self.model_path or not self.proj_path:
            return False
        if not os.path.exists(self.model_path) or not os.path.exists(self.proj_path):
            return False
        return True

    def _resize_image_for_inference(self, img: PIL.Image.Image, max_dim: int = 1024) -> str:
        """
        Resizes the image to a maximum dimension preserving aspect ratio.
        Returns the base64 encoded string of the resized image.
        """
        # Create a copy so we don't mutate the original image
        img_copy = img.copy()
        img_copy.thumbnail((max_dim, max_dim), PIL.Image.Resampling.LANCZOS)

        buffered = BytesIO()
        # Convert to RGB to ensure JPEG compatibility and strip alpha
        if img_copy.mode in ('RGBA', 'P', 'LA'):
            img_copy = img_copy.convert('RGB')

        img_copy.save(buffered, format="JPEG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def analyze(self, image: PIL.Image.Image, prompt: str) -> Dict[str, Any]:
        if not self.is_available():
            return {
                "ok": False,
                "error": "VISION_MODEL_UNAVAILABLE",
                "content": None
            }

        # Resource Governor Check
        if resource_governor.state == SystemState.EMERGENCY:
            return {
                "ok": False,
                "error": "SYSTEM_OVERLOADED",
                "content": None
            }

        if not self.lock.acquire(timeout=5.0):
            # Enforce 1 concurrent vision inference
            return {
                "ok": False,
                "error": "VISION_MODEL_BUSY",
                "content": None
            }

        try:
            # Lazy load the model
            if self._llama is None:
                try:
                    chat_handler = Llava15ChatHandler(clip_model_path=self.proj_path)
                    self._llama = Llama(
                        model_path=self.model_path,
                        chat_handler=chat_handler,
                        n_ctx=2048, # Enough for image + text prompt
                        n_gpu_layers=0, # Default to CPU unless configured otherwise (in B5)
                        verbose=False
                    )
                except Exception as e:
                    logger.error(f"Vision model load failed: {e}")
                    return {
                        "ok": False,
                        "error": "VISION_MODEL_LOAD_FAILED",
                        "content": None
                    }

            # Resize the image for VRAM safety
            base64_image = self._resize_image_for_inference(image)

            # Perform inference
            try:
                response = self._llama.create_chat_completion(
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                {"type": "text", "text": prompt}
                            ]
                        }
                    ],
                    max_tokens=256
                )

                content = response["choices"][0]["message"]["content"]
                return {
                    "ok": True,
                    "error": None,
                    "content": content
                }
            except Exception as e:
                logger.error(f"Vision inference failed: {e}")
                return {
                    "ok": False,
                    "error": "VISION_INFERENCE_FAILED",
                    "content": None
                }

        finally:
            self.lock.release()
