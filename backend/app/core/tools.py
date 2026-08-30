import psutil
import json
from app.core.tool_registry import tool_registry, ToolDefinition, ToolSchema, RiskTier


def get_system_telemetry():
    """Returns the current CPU and RAM usage as a JSON string."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    ram_usage = mem.percent
    ram_gb = mem.used / (1024 ** 3)
    ram_total_gb = mem.total / (1024 ** 3)
    
    return json.dumps({
        "cpu_percent": cpu,
        "ram_percent": ram_usage,
        "ram_used_gb": round(ram_gb, 2),
        "ram_total_gb": round(ram_total_gb, 2)
    })


def search_web(query: str):
    """Searches the internet and returns summaries."""
    from app.core.research_service import research_service
    return research_service.search(query)


# Register search_web and get_system_telemetry in the Security Gate
tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="search_web",
        description="Searches the live internet and returns factual summaries.",
        risk_tier=RiskTier.TIER_1,
        parameters={"query": {"type": "string"}}
    ),
    executor=search_web
))

tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="get_system_telemetry",
        description="Returns CPU and RAM usage metrics.",
        risk_tier=RiskTier.TIER_1,
        parameters={}
    ),
    executor=get_system_telemetry
))


def execute_tool(tool_name: str, args: dict, session_id: str, confirmation_token: str = None) -> str:
    """Dispatches ALL tool calls through the secure runner. No bypasses."""
    from app.core.secure_runner import secure_runner
    result = secure_runner.execute(tool_name, args, session_id, confirmation_token)
    return json.dumps(result)
