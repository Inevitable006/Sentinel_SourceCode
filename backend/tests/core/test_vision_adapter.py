import pytest
from PIL import Image
from app.core.vision_adapter import LocalVisionAdapter

def test_adapter_initializes():
    """Test that the local vision adapter initializes with valid configuration."""
    adapter = LocalVisionAdapter(model_path="dummy_path")
    assert adapter.model_path == "dummy_path"

def test_adapter_unavailable_by_default():
    """
    Test that the stub adapter is strictly unavailable in B4, 
    preventing any automatic model downloads or execution.
    """
    adapter = LocalVisionAdapter()
    assert adapter.is_available() is False

def test_adapter_handles_analyze_when_unavailable():
    """
    Test that analyzing with an unavailable adapter safely returns a
    controlled error structure and DOES NOT attempt model execution.
    """
    adapter = LocalVisionAdapter()
    dummy_img = Image.new('RGB', (10, 10))
    result = adapter.analyze(dummy_img, "Describe this image.")
    
    assert result["ok"] is False
    assert result["error"] == "VISION_MODEL_UNAVAILABLE"
    assert result["content"] is None
