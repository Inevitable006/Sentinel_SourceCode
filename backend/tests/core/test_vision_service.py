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
