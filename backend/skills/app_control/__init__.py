"""
Skill: app_control
Executes automation scripts inside external applications (e.g., Blender) locally.
Risk Tier: 3 (requires explicit user confirmation for code execution)
Capabilities: PROCESS_EXEC
"""
import os
import uuid
import shutil
from typing import Optional
from app.core.paths import SENTINEL_DATA_DIR
from app.core.safe_process import safe_process

def _find_blender_executable() -> Optional[str]:
    """Attempts to find the Blender executable path on the system."""
    # Check if blender is in PATH
    blender_path = shutil.which("blender")
    if blender_path:
        return blender_path
    
    # Check common Windows installation paths for various versions
    if os.name == 'nt':
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        blender_dir = os.path.join(program_files, "Blender Foundation")
        if os.path.exists(blender_dir):
            for version_dir in os.listdir(blender_dir):
                candidate = os.path.join(blender_dir, version_dir, "blender.exe")
                if os.path.exists(candidate):
                    return candidate
    
    # Fallback to standard Mac path
    mac_path = "/Applications/Blender.app/Contents/MacOS/Blender"
    if os.path.exists(mac_path):
        return mac_path

    return None

def run_blender_script(script_code: str, blend_file_path: Optional[str] = None, session_id: str = "default") -> str:
    """
    Executes a Python script (using bpy) inside a headless Blender instance.
    """
    blender_exe = _find_blender_executable()
    if not blender_exe:
        return "Execution Failed: Could not locate the 'blender' executable on the system."

    # Create the scratch directory if it doesn't exist
    scratch_dir = SENTINEL_DATA_DIR / "scratch"
    os.makedirs(scratch_dir, exist_ok=True)
    
    # Generate a unique temporary filename
    temp_filename = scratch_dir / f"blender_script_{uuid.uuid4().hex}.py"
    
    try:
        # Write the code to the temp file
        with open(temp_filename, "w", encoding="utf-8") as f:
            f.write(script_code)
            
        # Build the Blender headless command
        cmd = [blender_exe]
        
        # If a blend file is provided, open it, otherwise it opens a default startup file
        if blend_file_path:
            # We don't enforce _is_path_contained here because Tier 3 implies user confirmation
            # of the exact command being executed. The user can authorize modifying specific files.
            cmd.append(str(blend_file_path))
            
        cmd.extend(["--background", "--python", str(temp_filename)])
        
        success, stdout, stderr = safe_process.run_command(cmd, job_id=session_id)
        
        if success:
            output = stdout.strip()
            # Clean up the output to filter out standard Blender startup noise if desired, 
            # or just return the full output.
            return f"Blender executed successfully.\nOutput:\n{output}" if output else "Blender executed successfully with no output."
        else:
            return f"Blender Execution Failed:\n{stderr}\n{stdout}"
            
    except Exception as e:
        return f"System Error executing Blender script: {str(e)}"
        
    finally:
        # Ensure the temporary file is securely deleted
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except OSError:
                pass
