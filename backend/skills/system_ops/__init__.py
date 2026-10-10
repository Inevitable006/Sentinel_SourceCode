"""
Skill: system_ops
Structured system operations with strict operation allowlisting.
Risk Tier: 3 (requires user confirmation token)
Capabilities: PROCESS_EXEC
"""
import re
import os
import json
from datetime import datetime
from app.core.tool_registry import failed


def _is_path_contained(child: str, parent: str) -> bool:
    """Case-insensitive, symlink-resolving containment check."""
    from pathlib import Path
    try:
        child_resolved = Path(os.path.realpath(child)).resolve()
        parent_resolved = Path(os.path.realpath(parent)).resolve()
        child_resolved.relative_to(parent_resolved)
        return True
    except (ValueError, OSError):
        return False


def run_system_op(operation: str, target: str = "", session_id: str = "default"):
    """Executes a validated system operation from a fixed allowlist.
    No raw command execution — each operation is a hardcoded implementation."""
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
        from app.core.paths import workspace_root
        allowed_root = str(workspace_root())
        target_path = os.path.realpath(target) if target else os.path.realpath(allowed_root)

        if not _is_path_contained(target_path, allowed_root):
            return failed("Error: Path traversal blocked. Cannot access directories outside the approved workspace.")

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
            return failed(f"Error reading directory: {str(e)}")

    elif operation == "ping_host":
        if not re.match(r"^[\w\.-]+$", target):
            return failed("Error: Invalid hostname for ping.")
        cmd = [r"c:\windows\system32\ping.exe", "-n", "4", target]
        success, stdout, stderr = safe_process.run_command(cmd)
        return stdout if success else failed(stderr or "Error: command failed.")

    elif operation == "get_processes":
        cmd = ps_base + ["Get-Process | Select-Object Id, ProcessName, CPU, WorkingSet | ConvertTo-Json -Depth 1"]
        success, stdout, stderr = safe_process.run_command(cmd)
        return stdout if success else failed(stderr or "Error: command failed.")

    elif operation == "get_services":
        cmd = ps_base + ["Get-Service | Where-Object Status -eq 'Running' | Select-Object Name, DisplayName | ConvertTo-Json -Depth 1"]
        success, stdout, stderr = safe_process.run_command(cmd)
        return stdout if success else failed(stderr or "Error: command failed.")

    elif operation == "get_ip_configuration":
        cmd = ps_base + ["Get-NetIPAddress | Select-Object InterfaceAlias, IPAddress | ConvertTo-Json -Depth 1"]
        success, stdout, stderr = safe_process.run_command(cmd)
        return stdout if success else failed(stderr or "Error: command failed.")

    else:
        return failed(f"Error: Unknown operation '{operation}'")
