import time
import os
from app.core.safe_process import safe_process
from app.core.secure_runner import secure_runner
from app.core.policy_engine import policy_engine, PolicyDecision
from app.core.resource_governor import resource_governor, SystemState
from app.core.tool_registry import tool_registry

def test_safe_process_timeout():
    # Attempt to sleep for 5 seconds but enforce a 1 second timeout
    success, stdout, stderr = safe_process.run_command(
        ["powershell.exe", "-Command", "Start-Sleep -Seconds 5; Write-Output 'Done'"], 
        timeout_seconds=1
    )
    assert not success
    assert "timeout" in stderr.lower()

def test_safe_process_truncation():
    # Generate > 10KB of output
    success, stdout, stderr = safe_process.run_command(
        ["powershell.exe", "-Command", "for ($i=0; $i -lt 2000; $i++) { Write-Output 'This is a test line.' }"], 
        timeout_seconds=10
    )
    assert success
    assert len(stdout) <= (10 * 1024 + 100) # 10KB + truncation message
    assert stdout.endswith("limit]")

def test_path_traversal():
    assert safe_process.validate_path_safety("C:/valid/path") == True
    assert safe_process.validate_path_safety("../etc/passwd") == False
    assert safe_process.validate_path_safety("C:/Windows/../System32") == False

def test_powershell_tier3():
    # Policy should deny/require confirmation for run_system_op
    decision, reason = policy_engine.evaluate("run_system_op", {"operation": "get_processes"}, "test_session")
    assert decision == PolicyDecision.NEEDS_CONFIRMATION

def test_resource_governor_blocking():
    resource_governor.state = SystemState.EMERGENCY
    
    # Secure runner should abort entirely
    result = secure_runner.execute("get_service_health", {}, "test_session")
    print("GOVERNOR RESULT:", result)
    assert result["status"] == "error"
    assert "EMERGENCY" in result["message"] or "emergency" in result["message"].lower()
    
    resource_governor.state = SystemState.IDLE

if __name__ == "__main__":
    try:
        print("Running Phase 9 Adversarial & Orchestration Tests...")
        
        print("1. Testing safe_process timeout...", end="")
        test_safe_process_timeout()
        print("PASS")
        
        print("2. Testing safe_process output truncation...", end="")
        test_safe_process_truncation()
        print("PASS")
        
        print("3. Testing path traversal validation...", end="")
        test_path_traversal()
        print("PASS")
        
        print("4. Testing PowerShell RiskTier enforcement (Tier 3)...", end="")
        test_powershell_tier3()
        print("PASS")
        
        print("5. Testing Pre-Execution Resource Governor Blocking...", end="")
        test_resource_governor_blocking()
        print("PASS")
        
        print("\nAll Phase 9 basic tests passed.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FAILED: {e}")
