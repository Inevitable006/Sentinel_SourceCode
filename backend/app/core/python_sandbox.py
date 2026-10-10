"""Contained execution of owner-approved Python scripts.

Layers (none is relied on alone):
1. Explicit owner approval of the exact code (Tier 3 confirmation, enforced by SecureRunner).
2. A separate process: isolated mode (-I), no site-packages (-S), no bytecode writes (-B),
   minimal environment, working directory = the Sentinel Python workspace.
3. A Windows Job Object assigned before any code is sent: memory cap, one process only
   (no children), killed when the job handle closes.
4. An audit hook inside the child (sandbox_boot.py): no network, no new processes, no native
   code, reads limited to the standard library and the workspace, writes to the workspace only.
5. SafeProcess time limit, output budget and per-request cancellation.
Audit hooks are not an OS security boundary; this is a contained runner for the owner's own
approved scripts, not a sandbox for hostile code.
"""
import os
import sys
from pathlib import Path

from app.core.paths import SENTINEL_DATA_DIR
from app.core.safe_process import safe_process

WORKSPACE = SENTINEL_DATA_DIR / "python-workspace"
BOOT = Path(__file__).resolve().with_name("sandbox_boot.py")
MEMORY_LIMIT_BYTES = 512 * 1024 * 1024
TIMEOUT_SECONDS = 20


def interpreter() -> str:
    # The base interpreter, not the venv launcher (which would start a second process).
    return os.path.abspath(getattr(sys, "_base_executable", None) or sys.executable).lower()


class _Job:
    """Minimal Windows Job Object wrapper (ctypes, no extra dependency)."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.k32 = ctypes, ctypes.WinDLL("kernel32", use_last_error=True)
        self.k32.CreateJobObjectW.restype = wintypes.HANDLE
        self.k32.OpenProcess.restype = wintypes.HANDLE
        self.handle = self.k32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        info = EXTENDED()
        KILL_ON_JOB_CLOSE, ACTIVE_PROCESS, JOB_MEMORY, DIE_ON_EXCEPTION = 0x2000, 0x8, 0x200, 0x400
        info.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE | ACTIVE_PROCESS | JOB_MEMORY | DIE_ON_EXCEPTION
        info.BasicLimitInformation.ActiveProcessLimit = 1
        info.JobMemoryLimit = MEMORY_LIMIT_BYTES
        if not self.k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def assign(self, pid: int):
        PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001
        proc = self.k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not proc:
            raise OSError(self.ctypes.get_last_error(), "OpenProcess failed")
        try:
            if not self.k32.AssignProcessToJobObject(self.handle, proc):
                raise OSError(self.ctypes.get_last_error(), "AssignProcessToJobObject failed")
        finally:
            self.k32.CloseHandle(proc)

    def close(self):
        if self.handle:
            self.k32.CloseHandle(self.handle)   # kills anything still in the job
            self.handle = None


def run_python(code: str):
    """Returns (success, stdout, stderr). The caller has already obtained owner approval."""
    if os.name != "nt":
        return False, "", "Error: Contained Python execution is only implemented on Windows."
    if not BOOT.is_file():
        return False, "", "Error: The sandbox bootstrap is missing."
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    exe = interpreter()
    job = _Job()
    started = []

    def contain(process):
        job.assign(process.pid)   # before the script is written to stdin
        started.append(process.pid)

    try:
        return safe_process.run_command(
            [exe, "-I", "-S", "-B", str(BOOT), str(WORKSPACE)],
            timeout_seconds=TIMEOUT_SECONDS, cwd=str(WORKSPACE),
            extra_allowed=frozenset([exe]),
            env={"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"},
            stdin_bytes=code.encode("utf-8"), on_start=contain)
    finally:
        job.close()
