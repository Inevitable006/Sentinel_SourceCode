import time
from app.core.policy_engine import policy_engine, PolicyDecision
from app.core.secure_runner import secure_runner
from app.core.token_service import token_service
from app.core.resource_governor import resource_governor, SystemState
from app.core.audit_logger import AUDIT_LOG_FILE

def test_unknown_tool():
    decision, _ = policy_engine.evaluate("launch_nukes", {}, "test_session")
    assert decision == PolicyDecision.DENY

def test_invalid_schema():
    decision, _ = policy_engine.evaluate("get_service_health", {"extra_arg": "hack"}, "test_session")
    assert decision == PolicyDecision.DENY

def test_readonly_tool():
    decision, _ = policy_engine.evaluate("get_service_health", {}, "test_session")
    assert decision == PolicyDecision.ALLOW
    
    result = secure_runner.execute("get_service_health", {}, "test_session")
    assert result["status"] == "success"
    assert "running normally" in result["data"]

def test_confirmation_flow():
    # Attempt without token
    result1 = secure_runner.execute("test_confirmation_action", {"dummy_param": "hello"}, "test_session")
    assert result1["status"] == "needs_confirmation"
    token = result1["token"]
    
    # Attempt with bad token
    result2 = secure_runner.execute("test_confirmation_action", {"dummy_param": "hello"}, "test_session", token="BADTOKEN")
    assert result2["status"] == "error"
    
    # Attempt with changed arguments
    result3 = secure_runner.execute("test_confirmation_action", {"dummy_param": "changed"}, "test_session", token=token)
    assert result3["status"] == "error"
    
    # Attempt with valid token
    result4 = secure_runner.execute("test_confirmation_action", {"dummy_param": "hello"}, "test_session", token=token)
    assert result4["status"] == "success"
    assert "Dummy action completed" in result4["data"]
    
    # Attempt to reuse token (single-use)
    result5 = secure_runner.execute("test_confirmation_action", {"dummy_param": "hello"}, "test_session", token=token)
    assert result5["status"] == "error"

def test_governor_blocking():
    resource_governor.state = SystemState.EMERGENCY
    decision, _ = policy_engine.evaluate("get_service_health", {}, "test_session")
    assert decision == PolicyDecision.DENY
    resource_governor.state = SystemState.IDLE

def test_audit_log():
    # Make a dummy call to generate log
    secure_runner.execute("get_service_health", {"secret": "MY_PASSWORD"}, "test_session")
    with open(AUDIT_LOG_FILE, "r") as f:
        logs = f.read()
        assert "MY_PASSWORD" not in logs
        assert "[REDACTED]" in logs

if __name__ == "__main__":
    try:
        test_unknown_tool()
        print("PASS: Unknown tool denied")
        test_invalid_schema()
        print("PASS: Extra schema args denied")
        test_readonly_tool()
        print("PASS: Tier 1 Tool executed")
        test_confirmation_flow()
        print("PASS: Token flow validated (single-use, tamper-proof)")
        test_governor_blocking()
        print("PASS: Governor blocks tools in emergency")
        test_audit_log()
        print("PASS: Secrets redacted from audit log")
        print("\nAll Policy Engine tests passed.")
    except Exception as e:
        print(f"FAILED: {e}")
