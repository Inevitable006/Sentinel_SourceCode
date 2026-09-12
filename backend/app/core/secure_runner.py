from typing import Any, Dict
from app.core.tool_registry import tool_registry, ToolDefinition, ToolSchema, RiskTier
from app.core.policy_engine import policy_engine, PolicyDecision
from app.core.token_service import token_service
from app.core.audit_logger import audit_logger
import traceback
import psutil
import time

class SecureRunner:
    def execute(self, tool_name: str, args: dict, session_id: str, request_id: str = None, token: str = None) -> Dict[str, Any]:
        """Executes a tool with strict policy enforcement."""
        
        # 1. Policy Evaluation
        decision, reason = policy_engine.evaluate(tool_name, args, session_id)
        
        if decision == PolicyDecision.DENY:
            return {"status": "error", "message": f"Execution denied by policy: {reason}"}
            
        # 2. Token Validation for Needs Confirmation
        if decision == PolicyDecision.NEEDS_CONFIRMATION:
            if not token:
                # Generate token and return pause
                tool_def = tool_registry.get_tool(tool_name)
                req_token = token_service.generate_token(session_id, tool_name, args, tool_def.tool_schema.risk_tier.value)
                audit_logger.log_event("confirmation_requested", {"tool_name": tool_name, "args": args, "session_id": session_id})
                def get_risk_explanation(tier):
                    if tier == 1: return "Safe, read-only diagnostic action. No data modification."
                    if tier == 2: return "Reads approved local data. Data privacy applies."
                    if tier == 3: return "Modifies files or launches processes. Use caution."
                    if tier == 4: return "High-risk action. Can delete data or change system settings."
                    return "Unknown risk."

                return {
                    "status": "needs_confirmation", 
                    "message": "Action requires user confirmation.",
                    "token": req_token,
                    "action_preview": {
                        "tool": tool_name,
                        "title": tool_def.tool_schema.description.split('.')[0] if tool_def.tool_schema.description else tool_name,
                        "purpose": tool_def.tool_schema.description,
                        "target": str(args)[:100] + "..." if len(str(args)) > 100 else str(args),
                        "risk": tool_def.tool_schema.risk_tier.name,
                        "risk_explanation": get_risk_explanation(tool_def.tool_schema.risk_tier.value),
                        "expected_effect": "Executes the specified action on the local system.",
                        "is_reversible": tool_def.tool_schema.risk_tier.value <= 2,
                        "args": args
                    }
                }
            
            # Validate provided token
            if not token_service.validate_token(token, session_id, tool_name, args):
                audit_logger.log_event("token_validation_failed", {"tool_name": tool_name, "session_id": session_id})
                return {"status": "error", "message": "Invalid, expired, or mismatched confirmation token."}
                
        # 3. Execution
        tool_def = tool_registry.get_tool(tool_name)
        start_time = time.time()
        
        # Pre-execution Resource Governor check
        from app.core.resource_governor import resource_governor, SystemState
        if resource_governor.state in [SystemState.EMERGENCY, SystemState.USER_PAUSED]:
            return {"status": "error", "message": f"Execution aborted. System is in {resource_governor.state.value} state."}
            
        try:
            audit_logger.log_event("execution_started", {"tool_name": tool_name, "session_id": session_id})
            
            # Inject session_id or request_id into args if the executor supports it
            import inspect
            sig = inspect.signature(tool_def.executor)
            exec_args = args.copy()
            if "session_id" in sig.parameters:
                exec_args["session_id"] = session_id
            if "request_id" in sig.parameters:
                exec_args["request_id"] = request_id
                
            result = tool_def.executor(**exec_args)
            duration = time.time() - start_time
            
            # Truncate large outputs to prevent context overflow (10KB limit)
            result_str = str(result)
            if len(result_str) > 10240:
                result_str = result_str[:10240] + "... [TRUNCATED]"
                
            audit_logger.log_event("execution_success", {"tool_name": tool_name, "duration": duration, "session_id": session_id})
            return {"status": "success", "data": result_str}
            
        except Exception as e:
            duration = time.time() - start_time
            err_msg = str(e)
            audit_logger.log_event("execution_failed", {"tool_name": tool_name, "duration": duration, "error": err_msg, "session_id": session_id})
            return {"status": "error", "message": f"Tool execution failed: {err_msg}"}

secure_runner = SecureRunner()

# Register initial safe read-only tools
def get_service_health():
    return "Sentinel backend service is running normally."

def get_governor_status():
    from app.core.resource_governor import resource_governor
    return resource_governor.get_status()

def get_model_state():
    from app.core.ai_service import ai_service
    if ai_service.llm:
        return f"Model loaded: {ai_service.model_path} (Profile: {ai_service.active_profile['name']})"
    return "No model loaded."

def get_app_diagnostics():
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    return f"CPU Usage: {cpu}%. RAM Used: {mem.used / (1024**3):.2f} GB / {mem.total / (1024**3):.2f} GB."

def test_confirmation_action(dummy_param: str):
    return f"Dummy action completed with parameter: {dummy_param}"

tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="get_service_health",
        description="Returns the basic health status of the Sentinel backend.",
        risk_tier=RiskTier.TIER_1,
        parameters={}
    ),
    executor=get_service_health
))

tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="get_governor_status",
        description="Returns the current CPU/RAM Resource Governor state.",
        risk_tier=RiskTier.TIER_1,
        parameters={}
    ),
    executor=get_governor_status
))

tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="get_model_state",
        description="Returns the current local AI model state.",
        risk_tier=RiskTier.TIER_1,
        parameters={}
    ),
    executor=get_model_state
))

tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="get_app_diagnostics",
        description="Returns safe local resource metrics (CPU and RAM usage).",
        risk_tier=RiskTier.TIER_1,
        parameters={}
    ),
    executor=get_app_diagnostics
))

# Mock action for confirmation tests
tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="test_confirmation_action",
        description="A harmless dummy tool to test the Tier 3 confirmation protocol.",
        risk_tier=RiskTier.TIER_3,
        parameters={"dummy_param": {"type": "string"}}
    ),
    executor=test_confirmation_action
))

def _is_path_contained(child: str, parent: str) -> bool:
    """Case-insensitive, symlink-resolving containment check.
    
    Uses Path.relative_to() which raises ValueError if child is not
    a proper descendant of parent. This is immune to sibling-prefix
    attacks (e.g. 'ProjectEvil' passing a check for 'Project').
    """
    import os
    from pathlib import Path
    try:
        child_resolved = Path(os.path.realpath(child)).resolve()
        parent_resolved = Path(os.path.realpath(parent)).resolve()
        child_resolved.relative_to(parent_resolved)
        return True
    except (ValueError, OSError):
        return False

def run_system_op(operation: str, target: str = "", session_id: str = "default"):
    import re
    import os
    import json
    from datetime import datetime
    from app.core.safe_process import safe_process
    
    ps_base = [
        r"c:\windows\system32\windowspowershell\v1.0\powershell.exe", 
        "-NoProfile", 
        "-NonInteractive", 
        "-Command"
    ]
    
    if operation == "echo_text":
        # Native Python implementation (no shell injection possible)
        return target
        
    elif operation == "list_directory":
        # Native Python implementation (no shell injection possible)
        allowed_root = r"C:\Users\shamb\OneDrive\Desktop\New one\Sentinel_SourceCode"
        target_path = os.path.realpath(target) if target else os.path.realpath(allowed_root)
        
        # Path validation: canonical containment check immune to sibling-prefix,
        # case variation, symlink/junction, and traversal attacks
        if not _is_path_contained(target_path, allowed_root):
            return "Error: Path traversal blocked. Cannot access directories outside Sentinel_SourceCode."
            
        try:
            results = []
            for item in os.listdir(target_path):
                full_item = os.path.join(target_path, item)
                results.append({
                    "Name": item,
                    "Length": os.path.getsize(full_item) if os.path.isfile(full_item) else 0,
                    "LastWriteTime": datetime.fromtimestamp(os.path.getmtime(full_item)).isoformat()
                })
            return json.dumps(results)
        except Exception as e:
            return f"Error reading directory: {str(e)}"
            
    elif operation == "ping_host":
        # Native binary with safe argument array
        if not re.match(r"^[\w\.-]+$", target):
            return "Error: Invalid hostname for ping."
            
        cmd = [r"c:\windows\system32\ping.exe", "-n", "4", target]
        success, stdout, stderr = safe_process.run_command(cmd, job_id=session_id)
        return stdout if success else stderr
        
    elif operation == "get_processes":
        # Fixed PowerShell command string, absolutely ZERO interpolation
        cmd = ps_base + ["Get-Process | Select-Object Id, ProcessName, CPU, WorkingSet | ConvertTo-Json -Depth 1"]
        success, stdout, stderr = safe_process.run_command(cmd, job_id=session_id)
        return stdout if success else stderr
        
    elif operation == "get_services":
        # Fixed PowerShell command string, absolutely ZERO interpolation
        cmd = ps_base + ["Get-Service | Where-Object Status -eq 'Running' | Select-Object Name, DisplayName | ConvertTo-Json -Depth 1"]
        success, stdout, stderr = safe_process.run_command(cmd, job_id=session_id)
        return stdout if success else stderr
        
    elif operation == "get_ip_configuration":
        # Fixed PowerShell command string, absolutely ZERO interpolation
        cmd = ps_base + ["Get-NetIPAddress | Select-Object InterfaceAlias, IPAddress | ConvertTo-Json -Depth 1"]
        success, stdout, stderr = safe_process.run_command(cmd, job_id=session_id)
        return stdout if success else stderr
        
    else:
        return f"Error: Unknown operation '{operation}'"

tool_registry.register(ToolDefinition(
    tool_schema=ToolSchema(
        name="run_system_op",
        description="Executes a validated system operation. Operations: get_processes, get_services, get_ip_configuration, ping_host, list_directory, echo_text.",
        risk_tier=RiskTier.TIER_3,
        parameters={
            "operation": {
                "type": "string",
                "pattern": r"^(get_processes|get_services|get_ip_configuration|ping_host|list_directory|echo_text)$"
            },
            "target": {
                "type": "string"
            }
        }
    ),
    executor=run_system_op
))
