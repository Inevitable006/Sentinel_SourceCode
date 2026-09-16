import os
import tempfile
import pytest
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
