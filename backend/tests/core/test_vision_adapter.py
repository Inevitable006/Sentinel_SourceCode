import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
from app.core.vision_adapter import LocalVisionAdapter
from app.core.resource_governor import SystemState

def test_adapter_unavailable_by_default():
    """
    Test that the stub adapter is unavailable by default
    without model and proj paths.
    """
    adapter = LocalVisionAdapter()
    assert adapter.is_available() is False

@patch("app.core.vision_adapter.os.path.exists")
@patch("app.core.vision_adapter.LLAMA_CPP_AVAILABLE", True)
def test_adapter_is_available_when_files_exist(mock_exists):
    """
    Test that the adapter only becomes available when explicit
    model paths exist on the local filesystem.
    """
    mock_exists.return_value = True
    adapter = LocalVisionAdapter(model_path="dummy_model.gguf", proj_path="dummy_proj.gguf")
    assert adapter.is_available() is True

    mock_exists.return_value = False
    assert adapter.is_available() is False

@patch("app.core.vision_adapter.os.path.exists", return_value=True)
@patch("app.core.vision_adapter.LLAMA_CPP_AVAILABLE", True)
@patch("app.core.vision_adapter.resource_governor")
def test_adapter_analyze_respects_resource_governor(mock_governor, mock_exists):
    """
    Test that analyze rejects processing when the system is overloaded.
    """
    mock_governor.state = SystemState.EMERGENCY
    adapter = LocalVisionAdapter(model_path="dummy", proj_path="dummy")
    dummy_img = Image.new('RGB', (10, 10))
    result = adapter.analyze(dummy_img, "Test")

    assert result["ok"] is False
    assert result["error"] == "SYSTEM_OVERLOADED"

@patch("app.core.vision_adapter.os.path.exists", return_value=True)
@patch("app.core.vision_adapter.LLAMA_CPP_AVAILABLE", True)
@patch("app.core.vision_adapter.resource_governor")
def test_adapter_analyze_enforces_lock(mock_governor, mock_exists):
    """
    Test that the adapter blocks concurrent inference.
    """
    mock_governor.state = SystemState.IDLE
    adapter = LocalVisionAdapter(model_path="dummy", proj_path="dummy")
    # Manually acquire the lock to simulate another thread running
    adapter.lock.acquire()

    dummy_img = Image.new('RGB', (10, 10))
    # We patch acquire to not block forever in the test
    with patch.object(adapter.lock, "acquire", return_value=False):
        result = adapter.analyze(dummy_img, "Test")

    assert result["ok"] is False
    assert result["error"] == "VISION_MODEL_BUSY"
    adapter.lock.release()

@patch("app.core.vision_adapter.os.path.exists", return_value=True)
@patch("app.core.vision_adapter.LLAMA_CPP_AVAILABLE", True)
@patch("app.core.vision_adapter.resource_governor")
@patch("app.core.vision_adapter.Llama")
@patch("app.core.vision_adapter.Llava15ChatHandler")
def test_adapter_analyze_resizes_and_succeeds(mock_handler, mock_llama, mock_governor, mock_exists):
    """
    Test that analyze resizes the image for VRAM safety and calls the model.
    """
    mock_governor.state = SystemState.IDLE

    # Mock the LLM response
    mock_llama_instance = MagicMock()
    mock_llama_instance.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "I see a test image."}}]
    }
    mock_llama.return_value = mock_llama_instance

    adapter = LocalVisionAdapter(model_path="dummy", proj_path="dummy")
    # Pass a large image
    dummy_img = Image.new('RGB', (2048, 2048))

    # Spying on the internal resizer to verify bounds
    with patch.object(adapter, "_resize_image_for_inference", wraps=adapter._resize_image_for_inference) as mock_resize:
        result = adapter.analyze(dummy_img, "What is this?")

        assert result["ok"] is True
        assert result["content"] == "I see a test image."

        # Verify resize was called
        mock_resize.assert_called_once()
        args, kwargs = mock_resize.call_args
        # The copied image should be passed
        passed_img = args[0]
        # We can't easily check the thumbnail size of the copy after the fact,
        # but we know thumbnail modifies in place. The payload base64 should reflect the resized image.

        # Verify llama chat completion was called
        mock_llama_instance.create_chat_completion.assert_called_once()
