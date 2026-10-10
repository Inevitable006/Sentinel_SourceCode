"""
Skill: python_coding
Executes owner-approved Python code in a contained child process (app.core.python_sandbox):
separate isolated interpreter, Windows Job Object limits, no network, no new processes,
files limited to the Sentinel Python workspace, time and output budgets.
Risk Tier: 3 (requires explicit user confirmation for code execution)
Capabilities: PROCESS_EXEC
"""
from app.core.python_sandbox import run_python
from app.core.tool_registry import failed


def execute_python_code(code: str, session_id: str = "default") -> str:
    """
    Executes Python code in the contained runner and returns the output.
    """
    try:
        success, stdout, stderr = run_python(code)
    except Exception as e:
        return failed(f"System Error executing Python code: {str(e)}")
    if success:
        return stdout if stdout.strip() else "Code executed successfully with no output."
    return failed(f"Execution Failed:\n{stderr}")
