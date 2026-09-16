import os
import pathlib
from typing import Dict, Any
import PIL.Image
from PIL import UnidentifiedImageError
from app.core.vision_adapter import LocalVisionAdapter

class VisionService:
    # V1-B3: Hard resource limits
    MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
    MAX_WIDTH = 4096
    MAX_HEIGHT = 4096
    MAX_PIXELS = 4096 * 4096  # ~16.7 million pixels

    def __init__(self):
        self.allowed_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        # Enforce Pillow's native decompression bomb limit
        PIL.Image.MAX_IMAGE_PIXELS = self.MAX_PIXELS
        self.adapter = LocalVisionAdapter()

    def validate_image_path(self, image_path: str) -> bool:
        """
        V1-B1: Validates that an image path is a valid, existing local file
        with a permitted extension, and contains no traversal attempts.
        """
        if not image_path or not isinstance(image_path, str):
            return False

        # Check for obvious traversal attempts
        if ".." in image_path:
            return False

        try:
            # Use pathlib for robust parsing
            path = pathlib.Path(image_path).resolve(strict=False)

            # Re-check traversal post-resolution by ensuring the string form
            # doesn't do anything weird, though absolute resolution generally handles it.
            # We explicitly require the path to exist as a file.
            if not path.is_file():
                return False

            # Must have a valid extension
            ext = path.suffix.lower()
            if ext not in self.allowed_extensions:
                return False

            return True
        except Exception:
            # Any parsing errors (e.g., null bytes, OS errors) mean invalid path
            return False

    def load_image(self, image_path: str) -> PIL.Image.Image | None:
        """
        V1-B2: Securely loads an image into memory.
        Validates the path, verifies the image headers (preventing decompression bombs
        and parsing exploits on invalid files), and then fully decodes it.
        Returns the PIL Image object, or None if any failure occurs.
        """
        if not self.validate_image_path(image_path):
            return None

        # V1-B3.2: File-size enforcement before opening
        try:
            if os.path.getsize(image_path) > self.MAX_FILE_SIZE:
                return None
        except Exception:
            return None

        try:
            # Step 1: Safely open the image. This does not decode pixel data yet.
            with PIL.Image.open(image_path) as img:
                # Step 2: Verify the file structure.
                # This throws an exception if the file is corrupted, truncated, or not a real image.
                img.verify()

            # Step 3: Re-open the image because .verify() leaves the file pointer at the end.
            img = PIL.Image.open(image_path)

            # V1-B3.3: Dimension enforcement
            if img.width > self.MAX_WIDTH or img.height > self.MAX_HEIGHT:
                return None
            if (img.width * img.height) > self.MAX_PIXELS:
                return None

            # Step 4: Fully decode the pixel data into memory.
            # This ensures we have a valid, fully readable image bitmap.
            img.load()

            return img
        except PIL.Image.DecompressionBombError:
            # V1-B3.4: Safely reject decompression bombs
            return None
        except UnidentifiedImageError:
            # The file is not a valid image format
            return None
        except Exception:
            # Catch IOErrors, permission denied, missing files, or corrupted bitmap data
            return None

    def analyze_image(self, image_path: str, prompt: str) -> Dict[str, Any]:
        """
        V1-B4: Safely loads the image and forwards it to the vision adapter.
        Guarantees that B1-B3 validations are performed before adapter invocation.
        Returns a structured dictionary with the result.
        """
        # Step 1: B1-B3 Secure Loading
        img = self.load_image(image_path)
        if img is None:
            return {
                "ok": False,
                "error": "INVALID_IMAGE",
                "content": None
            }

        # Step 2: V1-B4 Adapter Boundary
        # The adapter itself checks for availability, but we enforce the contract here.
        if not self.adapter.is_available():
            # Clean up the loaded image before returning
            img.close()
            return {
                "ok": False,
                "error": "VISION_MODEL_UNAVAILABLE",
                "content": None
            }

        # Step 3: Forward to adapter (returns a structured dict)
        try:
            result = self.adapter.analyze(img, prompt)
            return result
        finally:
            # Always close the image after analysis
            img.close()

vision_service = VisionService()
