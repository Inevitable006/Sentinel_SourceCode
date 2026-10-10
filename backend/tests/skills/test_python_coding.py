import os
import pytest
from unittest.mock import patch
from app.core.tool_registry import is_failure
from skills.python_coding import execute_python_code

class TestPythonCoding:

    @patch("app.core.safe_process.safe_process.run_command")
    def test_execute_success(self, mock_run):
        mock_run.return_value = (True, "Hello from Python!\n", "")

        result = execute_python_code("print('Hello from Python!')")

        assert "Hello from Python!" in result
        assert not is_failure(result)
        mock_run.assert_called_once()

    @patch("app.core.safe_process.safe_process.run_command")
    def test_execute_failure(self, mock_run):
        mock_run.return_value = (False, "", "SyntaxError: invalid syntax")

        result = execute_python_code("prin('Hello')")

        assert "Execution Failed:" in result
        assert "SyntaxError" in result
        assert is_failure(result)

    @patch("app.core.safe_process.safe_process.run_command")
    def test_code_is_sent_on_stdin_not_written_to_disk(self, mock_run):
        # Replaces the old temp-file cleanup tests: the contained runner never writes the script to a file.
        mock_run.return_value = (True, "done", "")
        execute_python_code("print('test')")
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[1:4] == ["-I", "-S", "-B"]
        assert kwargs["stdin_bytes"] == b"print('test')"
        assert callable(kwargs["on_start"])          # job object assigned before code is sent
        assert not any(str(part).endswith(".py") and "script_" in str(part) for part in cmd)

    @patch("app.core.safe_process.safe_process.run_command")
    def test_crash_is_reported_as_failure(self, mock_run):
        mock_run.side_effect = RuntimeError("Simulated crash")
        result = execute_python_code("print('test')")
        assert "System Error executing Python code" in result
        assert is_failure(result)


@pytest.mark.skipif(os.name != "nt", reason="contained runner is Windows-only")
class TestContainedRunnerForReal:
    """No mocks: the real child process, job object and audit hook."""

    def test_harmless_script_runs_in_the_workspace(self):
        result = execute_python_code("open('note.txt', 'w').write('ok')\nprint(open('note.txt').read(), sum(range(5)))")
        assert not is_failure(result) and "ok 10" in result

    @pytest.mark.parametrize("code, reason", [
        ("open(r'C:\\Windows\\win.ini').read()", "cannot be read"),
        ("open(r'C:\\Users\\Public\\sentinel_sandbox_test.txt', 'w')", "only be written inside"),
        ("import socket", "'socket'"),
        ("import os; os.system('echo hi')", "os.system"),
        ("import subprocess", "'subprocess'"),
        ("import ctypes", "'ctypes'"),
    ])
    def test_outside_and_unapproved_operations_fail(self, code, reason):
        result = execute_python_code(code)
        assert is_failure(result) and reason in result
        assert not os.path.exists(r"C:\Users\Public\sentinel_sandbox_test.txt")

    def test_memory_cap(self):
        assert is_failure(execute_python_code("x = bytearray(900 * 1024 * 1024)"))
