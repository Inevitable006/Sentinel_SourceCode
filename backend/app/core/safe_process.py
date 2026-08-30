import subprocess
import os
import psutil
import time
import shutil
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Set

# Limit output to 10KB to prevent context window overflow
MAX_OUTPUT_BYTES = 10 * 1024

# Only explicitly configured absolute paths are permitted.
# This prevents PATH shadowing, alias bypassing, and extension tricks.
ALLOWED_EXECUTABLE_PATHS = frozenset([
    r"c:\windows\system32\windowspowershell\v1.0\powershell.exe",
    r"c:\windows\system32\nvidia-smi.exe",
    r"c:\program files\nvidia corporation\nvsmi\nvidia-smi.exe",
    r"c:\windows\system32\ping.exe"
])

class SafeProcessError(Exception):
    pass

class SafeProcessRunner:
    def __init__(self):
        # Maps job_id -> set of active PIDs
        self.active_processes: Dict[str, Set[int]] = {}

    def cancel_job(self, job_id: str):
        """Kills all active processes associated with a specific job/session."""
        if job_id in self.active_processes:
            pids = list(self.active_processes[job_id])
            for pid in pids:
                self._kill_process_tree(pid)
            self.active_processes[job_id].clear()

    def run_command(self, command: list, timeout_seconds: int = 15, cwd: str = None, job_id: str = "default") -> Tuple[bool, str, str]:
        """
        Runs a command safely, enforcing timeouts and output limits.
        Returns (success, stdout, stderr).
        """
        # Enforce canonical executable resolution
        if not command or not isinstance(command, list):
            return False, "", "Error: Invalid command format."
        
        raw_exe = command[0]
        # Reject relative paths immediately
        if "/" in raw_exe or ("\\" in raw_exe and not os.path.isabs(raw_exe)):
             return False, "", "Error: Relative executable paths are forbidden."
             
        # Resolve executable using standard PATH
        resolved_path = shutil.which(raw_exe)
        if not resolved_path:
            return False, "", f"Error: Executable '{raw_exe}' not found."
            
        canonical_path = os.path.abspath(resolved_path).lower()
        
        if canonical_path not in ALLOWED_EXECUTABLE_PATHS:
            return False, "", f"Error: Executable path '{canonical_path}' is not in the allowed list."
            
        # Ensure command uses the canonical absolute path
        safe_command = [canonical_path] + command[1:]
        
        # Create minimal environment
        safe_env = {
            "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "TEMP": os.environ.get("TEMP", r"C:\Temp")
        }
        
        try:
            # We use Popen so we can track the PID and kill the process tree if needed
            process = subprocess.Popen(
                safe_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=safe_env,
                text=True,
                shell=False,  # Explicitly forbid shell
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if job_id not in self.active_processes:
                self.active_processes[job_id] = set()
            self.active_processes[job_id].add(process.pid)
            
            try:
                stdout, stderr = process.communicate(timeout=timeout_seconds)
                success = (process.returncode == 0)
                
            except subprocess.TimeoutExpired:
                # Hard timeout hit. Kill the entire process tree.
                self._kill_process_tree(process.pid)
                process.communicate() # flush pipes
                return False, "", f"Error: Command exceeded timeout of {timeout_seconds} seconds and was terminated."
                
            finally:
                if job_id in self.active_processes and process.pid in self.active_processes[job_id]:
                    self.active_processes[job_id].remove(process.pid)

            # Enforce output truncation
            if len(stdout) > MAX_OUTPUT_BYTES:
                stdout = stdout[:MAX_OUTPUT_BYTES] + "\n... [TRUNCATED: Output exceeded 10KB limit]"
                
            if len(stderr) > MAX_OUTPUT_BYTES:
                stderr = stderr[:MAX_OUTPUT_BYTES] + "\n... [TRUNCATED: Error output exceeded 10KB limit]"

            return success, stdout, stderr

        except Exception as e:
            return False, "", f"Error executing process: {str(e)}"

    def _kill_process_tree(self, pid: int):
        """Recursively kills a process and all its children to prevent orphans."""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            print(f"Warning: Failed to kill process tree for PID {pid}: {e}")

    def validate_path_safety(self, path: str) -> bool:
        """
        Basic check to prevent obvious path traversal.
        Ensures the path does not attempt to go up directories.
        """
        if ".." in path:
            return False
        # In a full implementation, we'd resolve the path and check if it's within allowed boundaries
        return True

safe_process = SafeProcessRunner()
