import contextvars
import subprocess
import os
import psutil
import threading
import time
import shutil
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Set

# Limit returned output to 10KB to prevent context window overflow
MAX_OUTPUT_BYTES = 10 * 1024
# Hard budget for everything a process writes. Only MAX_OUTPUT_BYTES is ever kept in memory;
# a process that writes more than this is stopped (it is not just truncated afterwards).
MAX_CAPTURE_BYTES = 1024 * 1024

# Only explicitly configured absolute paths are permitted.
# This prevents PATH shadowing, alias bypassing, and extension tricks.
ALLOWED_EXECUTABLE_PATHS = frozenset([
    r"c:\windows\system32\windowspowershell\v1.0\powershell.exe",
    r"c:\windows\system32\nvidia-smi.exe",
    r"c:\program files\nvidia corporation\nvsmi\nvidia-smi.exe",
    r"c:\windows\system32\ping.exe"
])

# The request/job a tool is currently running for. SecureRunner sets it around every execution,
# so processes started anywhere inside a tool are tracked under the id that chat cancellation uses.
current_job: contextvars.ContextVar = contextvars.ContextVar("sentinel_current_job", default=None)


class SafeProcessError(Exception):
    pass


class _BoundedReader(threading.Thread):
    """Drains one pipe in chunks, keeps at most `keep` bytes and counts the rest."""
    def __init__(self, pipe, keep: int, on_overflow):
        super().__init__(daemon=True)
        self.pipe, self.keep, self.on_overflow = pipe, keep, on_overflow
        self.data = bytearray()
        self.total = 0

    def run(self):
        try:
            while True:
                chunk = self.pipe.read(8192)
                if not chunk:
                    break
                self.total += len(chunk)
                room = self.keep - len(self.data)
                if room > 0:
                    self.data += chunk[:room]
                if self.total > MAX_CAPTURE_BYTES:
                    self.on_overflow()
                    break
        except (OSError, ValueError):
            pass

    def text(self, label: str) -> str:
        out = self.data.decode("utf-8", errors="replace")
        if self.total > self.keep:
            out += f"\n... [TRUNCATED: {label} exceeded {self.keep // 1024}KB limit]"
        return out


class SafeProcessRunner:
    def __init__(self):
        # Maps job_id -> set of active PIDs
        self.active_processes: Dict[str, Set[int]] = {}
        self._lock = threading.Lock()

    def cancel_job(self, job_id: str):
        """Kills all active processes associated with a specific job (request) id."""
        with self._lock:
            pids = list(self.active_processes.get(job_id, ()))
        for pid in pids:
            self._kill_process_tree(pid)

    def _track(self, job_id: str, pid: int):
        with self._lock:
            self.active_processes.setdefault(job_id, set()).add(pid)

    def _untrack(self, job_id: str, pid: int):
        with self._lock:
            pids = self.active_processes.get(job_id)
            if pids is not None:
                pids.discard(pid)
                if not pids:
                    del self.active_processes[job_id]

    def resolve_allowed(self, raw_exe: str, extra_allowed: frozenset = frozenset()) -> Tuple[Optional[str], str]:
        """Returns (canonical path, "") or (None, error) for an executable."""
        if not raw_exe:
            return None, "Error: Invalid command format."
        # Reject relative paths immediately
        if "/" in raw_exe or ("\\" in raw_exe and not os.path.isabs(raw_exe)):
            return None, "Error: Relative executable paths are forbidden."
        resolved_path = shutil.which(raw_exe)
        if not resolved_path:
            return None, f"Error: Executable '{raw_exe}' not found."
        canonical_path = os.path.abspath(resolved_path).lower()
        if canonical_path not in ALLOWED_EXECUTABLE_PATHS and canonical_path not in extra_allowed:
            return None, f"Error: Executable path '{canonical_path}' is not in the allowed list."
        return canonical_path, ""

    def run_command(self, command: list, timeout_seconds: int = 15, cwd: str = None, job_id: Optional[str] = None,
                    extra_allowed: frozenset = frozenset(), env: Optional[dict] = None,
                    stdin_bytes: Optional[bytes] = None, on_start=None,
                    keep_bytes: int = MAX_OUTPUT_BYTES) -> Tuple[bool, str, str]:
        """
        Runs a command safely, enforcing timeouts and output budgets.
        Returns (success, stdout, stderr).
        `extra_allowed` lets a caller with its own containment (the sandboxed Python runner)
        add one specific canonical executable; it never widens the global allowlist.
        """
        if not command or not isinstance(command, list):
            return False, "", "Error: Invalid command format."
        job_id = job_id or current_job.get() or "default"
        canonical_path, error = self.resolve_allowed(command[0], extra_allowed)
        if not canonical_path:
            return False, "", error

        # Ensure command uses the canonical absolute path
        safe_command = [canonical_path] + command[1:]

        # Create minimal environment
        safe_env = {
            "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
            "PATH": os.environ.get("PATH", ""),
            "TEMP": os.environ.get("TEMP", r"C:\Temp")
        }
        if env:
            safe_env.update(env)

        try:
            # We use Popen so we can track the PID and kill the process tree if needed
            process = subprocess.Popen(
                safe_command,
                stdin=subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=safe_env,
                shell=False,  # Explicitly forbid shell
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
        except Exception as e:
            return False, "", f"Error executing process: {str(e)}"

        self._track(job_id, process.pid)
        overflowed = threading.Event()
        def overflow():
            overflowed.set()
            self._kill_process_tree(process.pid)
        try:
            if on_start:
                on_start(process)
            out = _BoundedReader(process.stdout, min(keep_bytes, MAX_CAPTURE_BYTES), overflow)
            err = _BoundedReader(process.stderr, MAX_OUTPUT_BYTES, overflow)
            out.start(); err.start()
            if stdin_bytes is not None:
                try:
                    process.stdin.write(stdin_bytes)
                    process.stdin.close()
                except OSError:
                    pass
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                # Hard timeout hit. Kill the entire process tree.
                self._kill_process_tree(process.pid)
                process.wait(5)
                out.join(2); err.join(2)
                return False, "", f"Error: Command exceeded timeout of {timeout_seconds} seconds and was terminated."
            out.join(5); err.join(5)
            if overflowed.is_set():
                return False, "", f"Error: Command output exceeded the {MAX_CAPTURE_BYTES // 1024} KB budget and was stopped."
            success = (process.returncode == 0)
            return success, out.text("Output"), err.text("Error output")
        except Exception as e:
            self._kill_process_tree(process.pid)
            return False, "", f"Error executing process: {str(e)}"
        finally:
            self._untrack(job_id, process.pid)
            for pipe in (process.stdout, process.stderr):
                try:
                    pipe.close()
                except Exception:
                    pass

    def _kill_process_tree(self, pid: int):
        """Recursively kills a process and all its children to prevent orphans."""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
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
