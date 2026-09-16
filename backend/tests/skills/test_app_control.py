import pytest
import os
from unittest.mock import patch, MagicMock
from app.core.skill_loader import skill_router

# Ensure app_control is loaded for tests
from skills.app_control import run_blender_script, _find_blender_executable

def test_find_blender_executable():
    # It should either return None or a string path
    path = _find_blender_executable()
    assert path is None or isinstance(path, str)

@patch("skills.app_control._find_blender_executable")
@patch("app.core.safe_process.safe_process.run_command")
def test_run_blender_script_success(mock_run_command, mock_find_blender):
    mock_find_blender.return_value = "C:\\mock\\blender.exe"
    mock_run_command.return_value = (True, "Blender output", "")
    
    script_code = "import bpy\nbpy.ops.mesh.primitive_cube_add()"
    result = run_blender_script(script_code=script_code, blend_file_path=None, session_id="test_sess")
    
    # Assert execution was successful
    assert "Blender executed successfully" in result
    assert "Blender output" in result
    
    # Verify the exact arguments passed to run_command
    mock_run_command.assert_called_once()
    args, kwargs = mock_run_command.call_args
    cmd = args[0]
    
    assert cmd[0] == "C:\\mock\\blender.exe"
    assert cmd[1] == "--background"
    assert cmd[2] == "--python"
    assert cmd[3].endswith(".py")
    assert "blender_script_" in cmd[3]

@patch("skills.app_control._find_blender_executable")
@patch("app.core.safe_process.safe_process.run_command")
def test_run_blender_script_with_file(mock_run_command, mock_find_blender):
    mock_find_blender.return_value = "C:\\mock\\blender.exe"
    mock_run_command.return_value = (True, "Success", "")
    
    result = run_blender_script(script_code="print('test')", blend_file_path="C:\\mock\\scene.blend", session_id="test_sess")
    
    mock_run_command.assert_called_once()
    args, kwargs = mock_run_command.call_args
    cmd = args[0]
    
    # Ensure blend file path is passed correctly
    assert cmd[0] == "C:\\mock\\blender.exe"
    assert cmd[1] == "C:\\mock\\scene.blend"
    assert cmd[2] == "--background"
    assert cmd[3] == "--python"

@patch("skills.app_control._find_blender_executable")
def test_run_blender_script_not_found(mock_find_blender):
    mock_find_blender.return_value = None
    
    result = run_blender_script(script_code="print('test')")
    
    assert "Execution Failed: Could not locate the 'blender' executable" in result
