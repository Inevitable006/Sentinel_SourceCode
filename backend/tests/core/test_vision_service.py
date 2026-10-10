import os
import tempfile
import pytest
from PIL import Image
from app.core.vision_service import vision_service

def test_validate_image_path_valid():
    """Test valid image path passes validation."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    try:
        assert vision_service.validate_image_path(temp_path) == True
    finally:
        os.remove(temp_path)

def test_validate_image_path_invalid_extension():
    """Test invalid extension (e.g., .txt) is rejected."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        temp_path = f.name
    try:
        assert vision_service.validate_image_path(temp_path) == False
    finally:
        os.remove(temp_path)

def test_validate_image_path_nonexistent_file():
    """Test file that does not exist is rejected."""
    fake_path = os.path.join(tempfile.gettempdir(), "nonexistent_fake_image.jpg")
    assert vision_service.validate_image_path(fake_path) == False

def test_validate_image_path_directory():
    """Test directory path is rejected."""
    temp_dir = tempfile.gettempdir()
    assert vision_service.validate_image_path(temp_dir) == False

def test_validate_image_path_traversal():
    """Test path containing '..' is rejected."""
    traversal_path = os.path.join(tempfile.gettempdir(), "..", "Windows", "System32", "cmd.exe")
    assert vision_service.validate_image_path(traversal_path) == False

def test_validate_image_path_empty_or_none():
    """Test empty string and None are rejected."""
    assert vision_service.validate_image_path("") == False
    assert vision_service.validate_image_path(None) == False

# --- load_image tests (V1-B2) ---

def create_dummy_image(path: str, fmt: str):
    img = Image.new('RGB', (10, 10), color='red')
    img.save(path, format=fmt)

def test_load_image_valid_formats():
    """Test loading valid PNG, JPG, WEBP, and BMP."""
    formats = [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP"), ("bmp", "BMP")]

    for ext, fmt in formats:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            temp_path = f.name
        try:
            create_dummy_image(temp_path, fmt)
            img = vision_service.load_image(temp_path)
            assert img is not None
            assert img.size == (10, 10)
        finally:
            os.remove(temp_path)

def test_load_image_corrupted():
    """Test that a file with a valid extension but non-image content is safely rejected."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"This is not a real image! Just some text pretending to be an image.")
        temp_path = f.name
    try:
        img = vision_service.load_image(temp_path)
        assert img is None
    finally:
        os.remove(temp_path)

def test_load_image_nonexistent():
    """Test loading a nonexistent file fails safely."""
    fake_path = os.path.join(tempfile.gettempdir(), "nonexistent_fake_image_2.jpg")
    img = vision_service.load_image(fake_path)
    assert img is None

def test_load_image_directory_masquerading():
    """Test loading a directory that ends in .png fails safely."""
    temp_dir = os.path.join(tempfile.gettempdir(), "fake_dir.png")
    os.makedirs(temp_dir, exist_ok=True)
    try:
        img = vision_service.load_image(temp_dir)
        assert img is None
    finally:
        os.rmdir(temp_dir)
# --- size and dimension limits (V1-B3) ---

def test_size_limit_rejected():
    """Test that a file exceeding MAX_FILE_SIZE is rejected."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        # Create a dummy file that is slightly larger than MAX_FILE_SIZE
        f.write(b'0' * (vision_service.MAX_FILE_SIZE + 1024))
        temp_path = f.name
    try:
        img = vision_service.load_image(temp_path)
        assert img is None
    finally:
        os.remove(temp_path)

def test_dimension_width_rejected():
    """Test that an image exceeding MAX_WIDTH is rejected."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    try:
        img = Image.new('RGB', (vision_service.MAX_WIDTH + 1, 10), color='red')
        img.save(temp_path, format="PNG")
        assert vision_service.load_image(temp_path) is None
    finally:
        os.remove(temp_path)

def test_dimension_height_rejected():
    """Test that an image exceeding MAX_HEIGHT is rejected."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    try:
        img = Image.new('RGB', (10, vision_service.MAX_HEIGHT + 1), color='red')
        img.save(temp_path, format="PNG")
        assert vision_service.load_image(temp_path) is None
    finally:
        os.remove(temp_path)

def test_dimension_pixels_rejected():
    """Test that an image exceeding MAX_PIXELS is rejected."""
    # Suppose MAX_WIDTH/HEIGHT is 4096 and MAX_PIXELS is 16M.
    # An image could be 4000x4200 (violates MAX_HEIGHT), but let's assume
    # we test exactly the pixel limit: 4096 * 4096 is the limit.
    # We can temporarily mock MAX_PIXELS to test this easily without generating a 16MB image.
    original_max_pixels = vision_service.MAX_PIXELS
    vision_service.MAX_PIXELS = 100 * 100
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    try:
        img = Image.new('RGB', (101, 100), color='red')  # 10100 pixels > 10000
        img.save(temp_path, format="PNG")
        assert vision_service.load_image(temp_path) is None
    finally:
        vision_service.MAX_PIXELS = original_max_pixels
        os.remove(temp_path)

def test_decompression_bomb_rejected():
    """Test that Pillow's decompression bomb protection is active and caught."""
    # We can trigger this by temporarily setting Image.MAX_IMAGE_PIXELS to a small value
    # and trying to load an image larger than that.
    import PIL.Image
    original_limit = PIL.Image.MAX_IMAGE_PIXELS
    PIL.Image.MAX_IMAGE_PIXELS = 100 * 100
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    try:
        # Create an image that exceeds the bomb limit but passes our naive checks
        # Actually our naive checks might catch it first if we don't bypass them.
        # But wait, Image.open() parses the headers and will throw DecompressionBombError
        # BEFORE our dimension checks run. Let's verify that.
        img = Image.new('RGB', (200, 200), color='red')
        # We need to save it while limits are normal so save doesn't crash
        PIL.Image.MAX_IMAGE_PIXELS = None
        img.save(temp_path, format="PNG")

        # Now restore the small limit and attempt load
        PIL.Image.MAX_IMAGE_PIXELS = 100 * 100
        # Load image should safely return None due to the bomb error
        assert vision_service.load_image(temp_path) is None
    finally:
        PIL.Image.MAX_IMAGE_PIXELS = original_limit
        os.remove(temp_path)
# --- analyze_image routing (V1-B4) ---

def test_analyze_image_invalid_image():
    """
    Test that analyze_image rejects invalid images (B1-B3 limits)
    before even hitting the adapter availability check.
    """
    # Create an invalid file
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        temp_path = f.name
    try:
        result = vision_service.analyze_image(temp_path, "Describe this")
        assert result["ok"] is False
        assert result["error"] == "INVALID_IMAGE"
    finally:
        os.remove(temp_path)

def test_analyze_image_valid_but_model_unavailable():
    """
    Test that passing a perfectly valid image through B1-B3 reaches the B4 adapter,
    and returns VISION_MODEL_UNAVAILABLE because the stub is offline.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        temp_path = f.name
    try:
        create_dummy_image(temp_path, "PNG")
        result = vision_service.analyze_image(temp_path, "Describe this")
        assert result["ok"] is False
        assert result["error"] == "VISION_MODEL_UNAVAILABLE"
    finally:
        os.remove(temp_path)
