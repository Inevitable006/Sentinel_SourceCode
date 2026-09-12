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
