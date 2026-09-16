import os
import pytest
from unittest.mock import patch
from app.core.paths import SENTINEL_DATA_DIR
from skills.python_coding import execute_python_code

class TestPythonCoding:
    
    @patch("app.core.safe_process.safe_process.run_command")
    def test_execute_success(self, mock_run):
        mock_run.return_value = (True, "Hello from Python!\n", "")
        
        result = execute_python_code("print('Hello from Python!')")
        
        assert "Hello from Python!" in result
        mock_run.assert_called_once()
        
    @patch("app.core.safe_process.safe_process.run_command")
    def test_execute_failure(self, mock_run):
        mock_run.return_value = (False, "", "SyntaxError: invalid syntax")
        
        result = execute_python_code("prin('Hello')")
        
        assert "Execution Failed:" in result
        assert "SyntaxError" in result
        
    @patch("app.core.safe_process.safe_process.run_command")
    def test_temp_file_cleanup(self, mock_run):
        mock_run.return_value = (True, "done", "")
        
        # We need to capture the filename used
        used_filename = None
        def mock_run_command(*args, **kwargs):
            nonlocal used_filename
            used_filename = args[0][1] # sys.executable is [0], filename is [1]
            assert os.path.exists(used_filename) # Should exist during run
            return (True, "done", "")
            
        mock_run.side_effect = mock_run_command
        
        execute_python_code("print('test')")
        
        # After execution, the file should be deleted
        assert used_filename is not None
        assert not os.path.exists(used_filename)

    @patch("app.core.safe_process.safe_process.run_command")
    def test_temp_file_cleanup_on_exception(self, mock_run):
        used_filename = None
        def mock_run_command(*args, **kwargs):
            nonlocal used_filename
            used_filename = args[0][1]
            raise RuntimeError("Simulated crash")
            
        mock_run.side_effect = mock_run_command
        
        result = execute_python_code("print('test')")
        
        assert "System Error executing Python code" in result
        assert used_filename is not None
        assert not os.path.exists(used_filename) # Still deleted on crash
