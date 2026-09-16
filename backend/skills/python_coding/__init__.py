"""
Skill: python_coding
Executes Python code locally in a sandboxed, time-bounded process.
Risk Tier: 3 (requires explicit user confirmation for code execution)
Capabilities: PROCESS_EXEC
"""
import os
import uuid
import sys
from app.core.paths import SENTINEL_DATA_DIR
from app.core.safe_process import safe_process

def execute_python_code(code: str, session_id: str = "default") -> str:
    """
    Executes Python code in a local subprocess and returns the output.
    """
    # Create the scratch directory if it doesn't exist
    scratch_dir = SENTINEL_DATA_DIR / "scratch"
    os.makedirs(scratch_dir, exist_ok=True)
    
    # Generate a unique temporary filename
    temp_filename = scratch_dir / f"script_{uuid.uuid4().hex}.py"
    
    try:
        # Write the code to the temp file
        with open(temp_filename, "w", encoding="utf-8") as f:
            f.write(code)
            
        # Execute the script using the current python executable (the venv)
        cmd = [sys.executable, str(temp_filename)]
        
        success, stdout, stderr = safe_process.run_command(cmd, job_id=session_id)
        
        if success:
            return stdout if stdout.strip() else "Code executed successfully with no output."
        else:
            return f"Execution Failed:\n{stderr}"
            
    except Exception as e:
        return f"System Error executing Python code: {str(e)}"
        
    finally:
        # Ensure the temporary file is securely deleted
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except OSError:
                pass
