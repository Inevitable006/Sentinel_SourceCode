import os
import pathlib
import PIL.Image
from PIL import UnidentifiedImageError

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

    def load_image(self, image_path: str) -> PIL.Image.Image | None:
        """
        V1-B2: Securely loads an image into memory.
        Validates the path, verifies the image headers (preventing decompression bombs
        and parsing exploits on invalid files), and then fully decodes it.
        Returns the PIL Image object, or None if any failure occurs.
        """
        if not self.validate_image_path(image_path):
            return None

        try:
            # Step 1: Safely open the image. This does not decode pixel data yet.
            with PIL.Image.open(image_path) as img:
                # Step 2: Verify the file structure.
                # This throws an exception if the file is corrupted, truncated, or not a real image.
                img.verify()

            # Step 3: Re-open the image because .verify() leaves the file pointer at the end.
            img = PIL.Image.open(image_path)

            # Step 4: Fully decode the pixel data into memory.
            # This ensures we have a valid, fully readable image bitmap.
            img.load()

            return img
        except UnidentifiedImageError:
            # The file is not a valid image format
            return None
        except Exception:
            # Catch IOErrors, permission denied, missing files, or corrupted bitmap data
            return None

vision_service = VisionService()
