import os
import pathlib

class VisionService:
    def __init__(self):
        self.allowed_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

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

vision_service = VisionService()
