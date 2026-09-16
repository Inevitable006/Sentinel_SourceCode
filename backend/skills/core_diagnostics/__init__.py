"""
Skill: core_diagnostics
Safe read-only tools for system health and status monitoring.
Risk Tier: 1 (auto-allowed, no confirmation needed)
"""
import psutil
import json


def get_service_health():
    """Returns the basic health status of the Sentinel backend."""
    return "Sentinel backend service is running normally."


def get_governor_status():
    """Returns the current CPU/RAM Resource Governor state."""
    from app.core.resource_governor import resource_governor
    return resource_governor.get_status()


def get_model_state():
    """Returns the current local AI model state."""
    from app.core.ai_service import ai_service
    if ai_service.llm:
        return f"Model loaded: {ai_service.model_path} (Profile: {ai_service.active_profile['name']})"
    return "No model loaded."


def get_app_diagnostics():
    """Returns safe local resource metrics (CPU and RAM usage)."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    return f"CPU Usage: {cpu}%. RAM Used: {mem.used / (1024**3):.2f} GB / {mem.total / (1024**3):.2f} GB."


def get_system_telemetry():
    """Returns the current CPU and RAM usage as a JSON string."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    return json.dumps({
        "cpu_percent": cpu,
        "ram_percent": mem.percent,
        "ram_used_gb": round(mem.used / (1024 ** 3), 2),
        "ram_total_gb": round(mem.total / (1024 ** 3), 2)
    })


def test_confirmation_action(dummy_param: str):
    """A harmless dummy tool to test the Tier 3 confirmation protocol."""
    return f"Dummy action completed with parameter: {dummy_param}"

import platform

_DISK_DEFAULT_PATH = "C:\\" if platform.system() == "Windows" else "/"


def get_disk_usage(path: str = _DISK_DEFAULT_PATH) -> dict:
    """
    Return disk usage for the given path.
    Defaults to the system root. Path must be an existing directory.
    Returns an error dict on PermissionError or invalid path.
    """
    import psutil

    # Reject obviously unsafe or unhelpful inputs
    path = str(path).strip()
    if not path:
        path = _DISK_DEFAULT_PATH

    try:
        usage = psutil.disk_usage(path)
        return {
            "path": path,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent_used": usage.percent,
        }
    except (PermissionError, FileNotFoundError, OSError) as exc:
        return {"error": type(exc).__name__, "path": path}


_VALID_SORT_FIELDS = {"cpu", "memory", "name"}
_SORT_KEY_MAP = {
    "cpu": "cpu_percent",
    "memory": "memory_percent",
    "name": "name",
}
_MAX_PROCESS_LIMIT = 50


def get_top_processes(limit: int = 10, sort_by: str = "cpu") -> list:
    """
    Return the top N running processes.

    sort_by: "cpu" | "memory" | "name"  — invalid values fall back to "cpu".
    limit:   clamped to 1–50.

    Exposes: pid, name, cpu_percent, memory_percent, status.
    Does NOT expose: command-line arguments, open files, user, environment.
    """
    # Validate and clamp inputs
    try:
        limit = min(max(1, int(limit)), _MAX_PROCESS_LIMIT)
    except (ValueError, TypeError):
        limit = 10

    if sort_by not in _VALID_SORT_FIELDS:
        sort_by = "cpu"

    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = proc.info
            processes.append({
                "pid": info["pid"],
                "name": info["name"] or "[unknown]",
                "cpu_percent": info["cpu_percent"] or 0.0,
                "memory_percent": round(info["memory_percent"] or 0.0, 2),
                "status": info["status"] or "unknown",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process may have exited between the list and the read — skip silently
            continue

    sort_key = _SORT_KEY_MAP[sort_by]
    reverse = sort_by != "name"
    processes.sort(key=lambda p: p[sort_key], reverse=reverse)
    return processes[:limit]


def get_network_stats() -> dict:
    """
    Return aggregate network I/O counters.

    Returns bytes, packets, errors, and drops — totals across all interfaces.
    Does NOT expose IP addresses, ports, or connection state.
    """
    import psutil

    io = psutil.net_io_counters()
    return {
        "bytes_sent_mb": round(io.bytes_sent / (1024 ** 2), 2),
        "bytes_recv_mb": round(io.bytes_recv / (1024 ** 2), 2),
        "packets_sent": io.packets_sent,
        "packets_recv": io.packets_recv,
        "errors_in": io.errin,
        "errors_out": io.errout,
        "drops_in": io.dropin,
        "drops_out": io.dropout,
    }


import subprocess


def get_gpu_status() -> dict:
    """
    Return GPU utilization and memory via nvidia-smi.

    No new Python dependency required.
    Returns {"available": False, "reason": "..."} for all failure modes.
    Never raises — all exceptions are caught and returned as structured output.
    """
    _QUERY = (
        "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu"
    )
    _CMD = [
        "nvidia-smi",
        f"--query-gpu={_QUERY}",
        "--format=csv,noheader,nounits",
    ]

    try:
        result = subprocess.run(
            _CMD,
            capture_output=True,
            text=True,
            timeout=5,
            # Never use shell=True — fixed argument list is safe
        )
    except FileNotFoundError:
        return {"available": False, "reason": "nvidia-smi not found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "nvidia-smi timed out"}
    except Exception as exc:
        return {"available": False, "reason": f"unexpected error: {type(exc).__name__}"}

    if result.returncode != 0:
        return {"available": False, "reason": "nvidia-smi returned non-zero exit code"}

    gpus = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        try:
            gpus.append({
                "index": int(parts[0]),
                "name": parts[1],
                "utilization_percent": int(parts[2]),
                "memory_used_mb": int(parts[3]),
                "memory_total_mb": int(parts[4]),
                "temperature_c": int(parts[5]),
            })
        except (ValueError, IndexError):
            continue  # Malformed line — skip, don't fail

    return {"available": True, "gpus": gpus}
